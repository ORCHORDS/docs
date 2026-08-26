# Email Rate Limit Per-Recipient D1 Sliding Window

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A single recipient receiving hundreds of automated emails per hour triggers spam complaints and blocklist hits. You need a fine-grained per-address rate limit enforced at send time inside a Cloudflare Worker, independent of your ESP's shared limits.

## Context
Cloudflare Workers can enforce a sliding-window counter using D1 with a single lightweight upsert and a row-level TTL scan, with no external Redis dependency. This approach tracks sends per recipient per window (e.g. 5 emails/hour, 20/day) and blocks or queues excess traffic before it reaches the ESP API. KV caches the allow/deny decision for the most recent 30 seconds to avoid D1 reads on every sub-second retry burst.

## D1 Schema

```sql
CREATE TABLE recipient_rate_limit (
  recipient       TEXT NOT NULL,
  window_key      TEXT NOT NULL,   -- e.g. "2026-08-23T14:00" (hourly) or "2026-08-23" (daily)
  window_type     TEXT NOT NULL,   -- "hourly" | "daily"
  count           INTEGER NOT NULL DEFAULT 0,
  expires_at      TEXT NOT NULL,   -- ISO-8601, used for pruning
  PRIMARY KEY (recipient, window_key, window_type)
);

CREATE INDEX idx_rrl_expires ON recipient_rate_limit(expires_at);
```

## Rate Limit Helper

```typescript
// rate-limit.ts
export interface Env {
  DB: D1Database;
  RL_CACHE: KVNamespace;
}

export interface RateLimitConfig {
  hourlyMax: number;
  dailyMax: number;
}

export interface RateLimitResult {
  allowed: boolean;
  hourlyCount: number;
  dailyCount: number;
  retryAfterSeconds?: number;
}

const DEFAULT_CONFIG: RateLimitConfig = { hourlyMax: 5, dailyMax: 20 };

function windowKeys(now: Date): { hourly: string; daily: string } {
  const iso = now.toISOString();
  return {
    hourly: iso.slice(0, 13).replace('T', 'T') + ':00', // "2026-08-23T14:00"
    daily: iso.slice(0, 10),                             // "2026-08-23"
  };
}

function expiresAt(windowType: 'hourly' | 'daily', now: Date): string {
  const d = new Date(now);
  if (windowType === 'hourly') d.setHours(d.getHours() + 2);
  else d.setDate(d.getDate() + 2);
  return d.toISOString();
}

export async function checkAndIncrement(
  recipient: string,
  env: Env,
  config: RateLimitConfig = DEFAULT_CONFIG
): Promise<RateLimitResult> {
  const cacheKey = `rl:${recipient}`;
  const cached = await env.RL_CACHE.get(cacheKey);
  if (cached) {
    const c = JSON.parse(cached) as RateLimitResult;
    if (!c.allowed) return c; // fast deny path
  }

  const now = new Date();
  const { hourly, daily } = windowKeys(now);

  // Upsert hourly window
  await env.DB.prepare(
    `INSERT INTO recipient_rate_limit (recipient, window_key, window_type, count, expires_at)
     VALUES (?, ?, 'hourly', 1, ?)
     ON CONFLICT (recipient, window_key, window_type)
     DO UPDATE SET count = count + 1`
  ).bind(recipient, hourly, expiresAt('hourly', now)).run();

  // Upsert daily window
  await env.DB.prepare(
    `INSERT INTO recipient_rate_limit (recipient, window_key, window_type, count, expires_at)
     VALUES (?, ?, 'daily', 1, ?)
     ON CONFLICT (recipient, window_key, window_type)
     DO UPDATE SET count = count + 1`
  ).bind(recipient, daily, expiresAt('daily', now)).run();

  // Read back both counts
  const rows = await env.DB.prepare(
    `SELECT window_type, count FROM recipient_rate_limit
     WHERE recipient = ? AND window_key IN (?, ?)
       AND window_type IN ('hourly', 'daily')`
  ).bind(recipient, hourly, daily).all<{ window_type: string; count: number }>();

  const hourlyCount = rows.results.find((r) => r.window_type === 'hourly')?.count ?? 1;
  const dailyCount = rows.results.find((r) => r.window_type === 'daily')?.count ?? 1;

  const hourlyDenied = hourlyCount > config.hourlyMax;
  const dailyDenied = dailyCount > config.dailyMax;
  const allowed = !hourlyDenied && !dailyDenied;

  // Compute retry-after (seconds until next window boundary)
  let retryAfterSeconds: number | undefined;
  if (hourlyDenied) {
    const nextHour = new Date(now);
    nextHour.setHours(nextHour.getHours() + 1, 0, 0, 0);
    retryAfterSeconds = Math.ceil((nextHour.getTime() - now.getTime()) / 1000);
  } else if (dailyDenied) {
    const nextDay = new Date(now);
    nextDay.setDate(nextDay.getDate() + 1);
    nextDay.setHours(0, 0, 0, 0);
    retryAfterSeconds = Math.ceil((nextDay.getTime() - now.getTime()) / 1000);
  }

  const result: RateLimitResult = { allowed, hourlyCount, dailyCount, retryAfterSeconds };

  // Cache for 30 s — deny results cache longer to deflect burst
  const ttl = allowed ? 30 : Math.min(retryAfterSeconds ?? 3600, 3600);
  await env.RL_CACHE.put(cacheKey, JSON.stringify(result), { expirationTtl: ttl });

  return result;
}
```

## Send Worker Integration

```typescript
// worker.ts
import { checkAndIncrement, Env } from './rate-limit';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { to, subject, html } = await request.json<{
      to: string;
      subject: string;
      html: string;
    }>();

    const rl = await checkAndIncrement(to.toLowerCase(), env, { hourlyMax: 5, dailyMax: 20 });

    if (!rl.allowed) {
      return Response.json(
        {
          error: 'Rate limit exceeded',
          hourlyCount: rl.hourlyCount,
          dailyCount: rl.dailyCount,
          retryAfterSeconds: rl.retryAfterSeconds,
        },
        {
          status: 429,
          headers: { 'Retry-After': String(rl.retryAfterSeconds ?? 3600) },
        }
      );
    }

    // Forward to ESP
    const espResponse = await fetch('https://api.mailchannels.net/tx/v1/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: to }] }],
        from: { email: 'noreply@yourdomain.com' },
        subject,
        content: [{ type: 'text/html', value: html }],
      }),
    });

    if (!espResponse.ok) {
      const text = await espResponse.text();
      return Response.json({ error: 'ESP send failed', detail: text }, { status: 502 });
    }

    return Response.json({ sent: true, hourlyCount: rl.hourlyCount, dailyCount: rl.dailyCount });
  },
};
```

## Pruning Cron

```typescript
// cleanup-cron.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Delete rows whose window has expired; run hourly
    const result = await env.DB.prepare(
      `DELETE FROM recipient_rate_limit WHERE expires_at < datetime('now')`
    ).run();
    console.log(`Pruned ${result.meta.changes} expired rate-limit rows`);
  },
};
```

```toml
# wrangler.toml excerpt
[[d1_databases]]
binding = "DB"
database_name = "email-rate-limit"
database_id = "YOUR_D1_ID"

[[kv_namespaces]]
binding = "RL_CACHE"
id = "YOUR_KV_ID"

[triggers]
crons = ["0 * * * *"]
```

## Anti-patterns
- Applying a single global rate limit per tenant rather than per recipient — a single high-volume recipient pollutes the shared quota for everyone else.
- Using `SELECT + UPDATE` as two separate statements without a transaction — a race condition between concurrent Workers invocations can allow the limit to be exceeded by the width of the race window; use `INSERT ... ON CONFLICT DO UPDATE` (upsert) as a single atomic statement instead.
- Storing the sliding window entirely in KV — KV's eventual consistency means a burst of concurrent requests all read a stale "count=0" before any increment propagates.
- Not caching the allow result — every outbound email triggering a D1 read adds 5-15 ms of latency; a 30-second KV cache is a safe compromise.
- Forgetting to decrement on ESP 4xx — if the ESP rejects the send (invalid address, etc.) the counter still fires; only increment after a successful send if your use case demands strict accuracy.

## Gotchas
- D1 `ON CONFLICT DO UPDATE` requires SQLite 3.24+; all D1 regions run a compatible version, but local `wrangler dev` must use `--local` with the bundled SQLite.
- The window key `"2026-08-23T14:00"` is always UTC; if your customers expect local-time windows (e.g. "no more than 5 per business-day morning"), you need to store their timezone in a tenants table and convert.
- KV `expirationTtl` must be at least 60 seconds — caching a deny result for 30 s triggers a KV validation error; clamp to 60.
- Pruning in a cron does not shrink the D1 page file on disk; run `VACUUM` quarterly via a separate admin endpoint if storage billing is a concern.
- If a recipient changes their email address, old rate-limit rows accumulate harmlessly but may cause confusion when debugging; include `recipient` in your log output.

## Verification
1. Send 6 emails to the same recipient in one minute; the 6th should return HTTP 429 with `Retry-After`.
2. Inspect `recipient_rate_limit` in D1 console: confirm `count = 6` for the hourly row and `count = 6` for the daily row.
3. Wait for the next UTC hour and retry; the hourly counter should reset while the daily counter remains.
4. Check KV namespace for the cached deny entry and confirm its TTL is ≤ 3600 seconds.
5. Trigger the cron manually (`wrangler cron trigger`) and confirm expired rows are deleted.

## Related
- `transactional-email-rate-limiting-workers.md`
- `email-bounce-storm-circuit-breaker-workers.md`
- `email-suppression-list-kv-workers.md`
- `email-engagement-score-decay-cron-workers.md`

## Sources
- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/lang_UPSERT.html
- https://developers.cloudflare.com/workers/runtime-apis/kv/
