# Per-Recipient Email Rate Limiting in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker that sends transactional email is being abused: a single recipient
address is being spammed by repeated API calls or a bug in retry logic. You need
to enforce a sliding-window rate limit keyed by recipient address, return HTTP
429 with a `Retry-After` header when the limit is exceeded, and log every blocked
attempt to D1 for audit purposes.

## Context

Cloudflare KV is ideal for fast, globally-consistent counters with TTL. A
sliding-window counter stores the current window's send count under a key like
`ratelimit:email:<recipient>:<window>`. D1 is used for the audit log because KV
does not support range queries needed for reporting.

---

## Section 1 – Rate Limit Configuration

```typescript
// src/lib/rate-limit/config.ts

export const RATE_LIMIT_CONFIG = {
  /** Maximum emails per recipient per window */
  maxPerWindow: 5,
  /** Window duration in seconds */
  windowSeconds: 3600, // 1 hour
} as const;

export function windowKey(recipient: string, windowStart: number): string {
  // Normalize recipient to lowercase to avoid case-based bypass
  const normalizedRecipient = recipient.toLowerCase().trim();
  return `ratelimit:email:${normalizedRecipient}:${windowStart}`;
}

export function currentWindowStart(nowSeconds: number, windowSeconds: number): number {
  return Math.floor(nowSeconds / windowSeconds) * windowSeconds;
}
```

---

## Section 2 – KV Sliding Window Counter

```typescript
// src/lib/rate-limit/counter.ts

import { RATE_LIMIT_CONFIG, windowKey, currentWindowStart } from './config';

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetAt: number;   // Unix timestamp when the window resets
  retryAfter: number; // seconds until allowed again (0 if allowed)
}

export async function checkAndIncrementRateLimit(
  kv: KVNamespace,
  recipient: string
): Promise<RateLimitResult> {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const windowStart = currentWindowStart(nowSeconds, RATE_LIMIT_CONFIG.windowSeconds);
  const resetAt = windowStart + RATE_LIMIT_CONFIG.windowSeconds;
  const key = windowKey(recipient, windowStart);

  // Read current count
  const raw = await kv.get(key);
  const current = raw !== null ? parseInt(raw, 10) : 0;

  if (current >= RATE_LIMIT_CONFIG.maxPerWindow) {
    return {
      allowed: false,
      remaining: 0,
      resetAt,
      retryAfter: resetAt - nowSeconds,
    };
  }

  // Increment with TTL aligned to window expiry + 60s buffer
  const ttl = resetAt - nowSeconds + 60;
  await kv.put(key, String(current + 1), { expirationTtl: ttl });

  return {
    allowed: true,
    remaining: RATE_LIMIT_CONFIG.maxPerWindow - (current + 1),
    resetAt,
    retryAfter: 0,
  };
}
```

---

## Section 3 – D1 Audit Log

```sql
-- migrations/0001_email_rate_limit_log.sql

CREATE TABLE IF NOT EXISTS email_rate_limit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  recipient   TEXT    NOT NULL,
  action      TEXT    NOT NULL CHECK(action IN ('allowed', 'blocked')),
  window_key  TEXT    NOT NULL,
  count_at    INTEGER NOT NULL,  -- count at the time of the check
  checked_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_email_rate_limit_log_recipient
  ON email_rate_limit_log(recipient, checked_at);
```

```typescript
// src/lib/rate-limit/audit.ts

import { windowKey, currentWindowStart, RATE_LIMIT_CONFIG } from './config';

export async function logRateLimitEvent(
  db: D1Database,
  recipient: string,
  action: 'allowed' | 'blocked',
  count: number
): Promise<void> {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const windowStart = currentWindowStart(nowSeconds, RATE_LIMIT_CONFIG.windowSeconds);
  const key = windowKey(recipient, windowStart);

  await db
    .prepare(
      `INSERT INTO email_rate_limit_log (recipient, action, window_key, count_at)
       VALUES (?, ?, ?, ?)`
    )
    .bind(recipient, action, key, count)
    .run();
}
```

---

## Section 4 – Middleware: Rate Limit Guard

```typescript
// src/lib/rate-limit/guard.ts

import { checkAndIncrementRateLimit } from './counter';
import { logRateLimitEvent } from './audit';

export async function rateLimitGuard(
  kv: KVNamespace,
  db: D1Database,
  recipient: string
): Promise<Response | null> {
  const result = await checkAndIncrementRateLimit(kv, recipient);

  if (!result.allowed) {
    // Fire-and-forget D1 write — don't block the 429 response
    logRateLimitEvent(db, recipient, 'blocked', 0).catch(console.error);

    return new Response(
      JSON.stringify({
        error: 'rate_limited',
        message: `Too many emails to this recipient. Retry after ${result.retryAfter} seconds.`,
        retry_after: result.retryAfter,
        reset_at: result.resetAt,
      }),
      {
        status: 429,
        headers: {
          'Content-Type': 'application/json',
          'Retry-After': String(result.retryAfter),
          'X-RateLimit-Limit': String(5),
          'X-RateLimit-Remaining': '0',
          'X-RateLimit-Reset': String(result.resetAt),
        },
      }
    );
  }

  // Log allowed sends (can be sampled to reduce D1 writes)
  logRateLimitEvent(
    db, recipient, 'allowed',
    5 - result.remaining
  ).catch(console.error);

  return null; // continue processing
}
```

---

## Section 5 – Worker Entry Point

```typescript
// src/index.ts

import { rateLimitGuard } from './lib/rate-limit/guard';

export interface Env {
  RATE_LIMIT_KV: KVNamespace;
  DB: D1Database;
  FROM_ADDRESS: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.json<{ to: string; subject: string; text: string }>();

    // Apply rate limit before doing anything expensive
    const limitResponse = await rateLimitGuard(env.RATE_LIMIT_KV, env.DB, body.to);
    if (limitResponse) return limitResponse;

    // Send via MailChannels
    const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: body.to }] }],
        from: { email: env.FROM_ADDRESS },
        subject: body.subject,
        content: [{ type: 'text/plain', value: body.text }],
      }),
    });

    if (!res.ok) {
      return new Response(`Send failed: ${res.status}`, { status: 502 });
    }

    return new Response(JSON.stringify({ ok: true }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id     = "YOUR_KV_NAMESPACE_ID"

[[d1_databases]]
binding  = "DB"
database_name = "my-db"
database_id   = "YOUR_D1_DATABASE_ID"
```

---

## Anti-patterns

- **Using a simple counter without TTL** – stale keys accumulate and consume KV
  storage quota indefinitely.
- **Keying only by IP** – a sender can rotate IPs trivially; key by recipient.
- **Blocking D1 writes before returning 429** – adds latency to the error path;
  use fire-and-forget or a Queue.
- **Setting `expirationTtl` less than the window duration** – counters expire
  mid-window and reset early, allowing limit bypass.

## Gotchas

- KV `put` with `expirationTtl` must be >= 60 seconds; shorter values are
  rejected with a 400 error.
- KV eventual consistency means a brief burst slightly above the limit is
  possible across edge PoPs. For strict enforcement use Durable Objects.
- D1 writes from Workers are subject to a 50 ms CPU time limit per request;
  audit writes should be non-blocking.
- The `Retry-After` header value should be in seconds (integer string), not
  an HTTP-date, for compatibility with all clients.

## Verification

```bash
# Exhaust the limit
for i in $(seq 1 6); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://your-worker.example.com/ \
    -H 'Content-Type: application/json' \
    -d '{"to":"target@example.com","subject":"Test","text":"Hello"}'
done
# Expected output: 200 200 200 200 200 429

# Inspect the audit log
wrangler d1 execute MY_DB --command \
  "SELECT action, count(*) FROM email_rate_limit_log GROUP BY action;"
```

## Related

- `workers-email-threading-message-id.md`
- `workers-email-scheduled-digest-cron.md`
- `workers-email-pgp-signature-verification.md`

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/d1/
- RFC 6585 §4 – 429 Too Many Requests
- https://developers.cloudflare.com/durable-objects/ (for strict enforcement)
