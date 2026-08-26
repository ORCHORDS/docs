# Transactional Email Idempotency with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A payment confirmation email fires twice because the checkout service retried an HTTP call to your
send endpoint. Or a Worker retried after a transient D1 write error even though the email was already
delivered. Customers receive duplicate receipts, password resets, or shipping notifications —
destroying trust.

## Context

Idempotency for email means: given the same logical event, the email is sent exactly once regardless
of how many times the trigger fires. The pattern stores a deterministic **idempotency key** (derived
from the event, not a random UUID) in D1 before sending. Subsequent calls with the same key return
the stored outcome without re-sending. Keys expire after a configurable TTL.

This is distinct from `email-webhook-idempotency-deduplication.md`, which covers deduplication of
inbound webhook payloads. This article covers the outbound send path.

---

## 1. Idempotency Key Design

```typescript
// src/idempotency-key.ts

/**
 * Derive a stable key from event properties.
 * DO NOT use random UUIDs — the caller must supply the same key on every retry.
 *
 * Examples:
 *   orderConfirmation  → `order:${orderId}:confirm`
 *   passwordReset      → `user:${userId}:pwd-reset:${Math.floor(Date.now() / 3_600_000)}`
 *   shippingNotice     → `shipment:${shipmentId}:notify`
 */
export function deriveKey(namespace: string, ...parts: string[]): string {
  return [namespace, ...parts].join(':');
}
```

---

## 2. D1 Schema

```sql
CREATE TABLE email_idempotency (
  ikey        TEXT PRIMARY KEY,
  status      TEXT NOT NULL,          -- 'sending' | 'sent' | 'failed'
  provider_id TEXT,                   -- e.g. Resend message ID
  error       TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at  TEXT NOT NULL           -- ISO-8601; enforced by cleanup cron
);

CREATE INDEX idx_ei_expires ON email_idempotency(expires_at);
```

---

## 3. Core Idempotency Guard

```typescript
// src/idempotency.ts
import type { Env } from './types';

export type IdempotencyRecord = {
  ikey: string;
  status: 'sending' | 'sent' | 'failed';
  provider_id: string | null;
  error: string | null;
};

const DEFAULT_TTL_HOURS = 72;

/**
 * Try to claim the idempotency key.
 * Returns null if the key is fresh (claim succeeded).
 * Returns an existing record if the key was already used.
 * Throws if D1 is unavailable.
 */
export async function claimKey(
  ikey: string,
  env: Env,
  ttlHours = DEFAULT_TTL_HOURS
): Promise<IdempotencyRecord | null> {
  const expiresAt = new Date(
    Date.now() + ttlHours * 3_600_000
  ).toISOString();

  // Attempt atomic INSERT; fails silently on conflict (IGNORE)
  const { meta } = await env.DB.prepare(
    `INSERT OR IGNORE INTO email_idempotency (ikey, status, expires_at)
     VALUES (?, 'sending', ?)`
  ).bind(ikey, expiresAt).run();

  if (meta.changes === 1) return null; // fresh claim

  // Key already exists — return current state
  return env.DB.prepare(
    `SELECT ikey, status, provider_id, error
     FROM email_idempotency WHERE ikey = ?`
  ).bind(ikey).first<IdempotencyRecord>();
}

export async function resolveKey(
  ikey: string,
  providerId: string,
  env: Env
): Promise<void> {
  await env.DB.prepare(
    `UPDATE email_idempotency
     SET status = 'sent', provider_id = ?
     WHERE ikey = ?`
  ).bind(providerId, ikey).run();
}

export async function failKey(
  ikey: string,
  error: string,
  env: Env
): Promise<void> {
  await env.DB.prepare(
    `UPDATE email_idempotency
     SET status = 'failed', error = ?
     WHERE ikey = ?`
  ).bind(error.slice(0, 512), ikey).run();
}
```

---

## 4. Send Wrapper with Idempotency

```typescript
// src/send.ts
import { claimKey, resolveKey, failKey } from './idempotency';
import type { Env } from './types';

export interface SendResult {
  providerId: string | null;
  duplicate: boolean;
  status: 'sent' | 'failed' | 'sending';
}

export async function sendIdempotent(
  ikey: string,
  to: string,
  subject: string,
  html: string,
  env: Env
): Promise<SendResult> {
  // 1. Claim or retrieve existing record
  const existing = await claimKey(ikey, env);

  if (existing) {
    // Already processed (or currently in-flight)
    return {
      providerId: existing.provider_id,
      duplicate: true,
      status: existing.status,
    };
  }

  // 2. Send via Resend (swap for any provider)
  try {
    const resp = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ from: env.FROM_ADDRESS, to, subject, html }),
    });

    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`Resend ${resp.status}: ${body}`);
    }

    const { id } = (await resp.json()) as { id: string };
    await resolveKey(ikey, id, env);

    return { providerId: id, duplicate: false, status: 'sent' };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    await failKey(ikey, msg, env);
    throw err;
  }
}
```

---

## 5. HTTP Endpoint with Idempotency-Key Header

```typescript
// src/worker.ts
import { sendIdempotent } from './send';
import { deriveKey } from './idempotency-key';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    // Callers MUST supply a deterministic key
    const ikey =
      request.headers.get('Idempotency-Key') ??
      deriveKey('fallback', crypto.randomUUID()); // random = no dedup guarantee

    const { to, subject, html } = await request.json<{
      to: string; subject: string; html: string;
    }>();

    const result = await sendIdempotent(ikey, to, subject, html, env);

    return Response.json(result, {
      status: result.duplicate ? 200 : 201,
      headers: { 'Idempotency-Key': ikey },
    });
  },
};
```

---

## 6. Expired Key Cleanup Cron

```typescript
// Runs daily; add to scheduled() handler
export async function cleanupExpiredKeys(env: Env): Promise<void> {
  await env.DB.prepare(
    `DELETE FROM email_idempotency WHERE expires_at < datetime('now')`
  ).run();
}
```

---

## 7. Handling the 'sending' Race

A key stuck in `'sending'` means a Worker crashed mid-send. Add a staleness check:

```typescript
export async function claimOrStaleSend(
  ikey: string, env: Env
): Promise<IdempotencyRecord | null> {
  const existing = await claimKey(ikey, env);
  if (!existing) return null;

  // If stuck 'sending' for >5 minutes, treat as failed and allow retry
  if (existing.status === 'sending') {
    const { results } = await env.DB.prepare(
      `SELECT 1 FROM email_idempotency
       WHERE ikey = ? AND created_at < datetime('now', '-5 minutes')`
    ).bind(ikey).all();

    if (results.length > 0) {
      await env.DB.prepare(
        `DELETE FROM email_idempotency WHERE ikey = ?`
      ).bind(ikey).run();
      return null; // allow retry
    }
  }
  return existing;
}
```

---

## Anti-patterns

- **Using random UUIDs as idempotency keys**: Each call generates a fresh key — deduplication never fires.
- **Storing keys only in KV**: KV's eventual consistency allows races on concurrent writes; D1's SQLite `INSERT OR IGNORE` is atomic.
- **No TTL**: Keys accumulate indefinitely; D1 row count and storage costs grow unbounded.
- **Catching errors but not calling `failKey`**: Key stays `'sending'` forever, blocking all future sends for that event.

## Gotchas

- `INSERT OR IGNORE` in SQLite silently discards the row on conflict and returns `changes = 0`; this is the intended behaviour here.
- D1's `first()` returns `null` when no row matches — always null-check before accessing fields.
- A 5xx from Resend does **not** guarantee the email was not sent; check Resend's activity log before resending if you see `status 500`.
- Callers must use the same `Idempotency-Key` value on every retry of the same logical event; document this contract in your API spec.

## Verification

```bash
# Confirm a key was recorded
wrangler d1 execute email-db --command \
  "SELECT ikey, status, provider_id, created_at FROM email_idempotency ORDER BY created_at DESC LIMIT 5"

# Simulate duplicate call (should return duplicate:true)
curl -X POST https://your-worker.dev/send \
  -H "Idempotency-Key: order:abc123:confirm" \
  -H "Content-Type: application/json" \
  -d '{"to":"test@example.com","subject":"Test","html":"<p>hi</p>"}'
# Call again with same key — expect 200 + duplicate:true
```

## Related

- `email-webhook-idempotency-deduplication.md`
- `email-retry-exponential-backoff.md`
- `email-bounce-storm-circuit-breaker-workers.md`
- `transactional-email-dead-letter-queue-workers.md`
- `email-thread-deduplication-queues-d1.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/lang_conflict.html
- https://resend.com/docs/api-reference/emails/send-email
- https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header
