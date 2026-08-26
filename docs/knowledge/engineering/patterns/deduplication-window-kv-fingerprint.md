# Deduplication Window Pattern — KV Fingerprint Store

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers endpoint or queue consumer receives the same logical message more than once —
from retry logic, at-least-once delivery guarantees, or network-layer replays.
Processing the duplicate causes duplicate charges, duplicate emails, or duplicate records
in D1.  You need a fast, cheap fence that rejects a message whose *content fingerprint*
has already been seen within a rolling time window.

---

## Context

Cloudflare KV is globally eventually-consistent and has a millisecond-range P99 read
latency, making it a natural fingerprint store for dedup windows of minutes to days.
This pattern differs from the **Idempotency Key** pattern (which deduplicates on a
caller-supplied key) because here the fingerprint is *derived from the message itself*,
which is useful when callers cannot or do not send a stable idempotency token.

Key constraints to keep in mind:
- KV writes are eventually consistent; a tight (< 60 s) window may admit duplicates
  in the brief propagation period.
- KV has no atomic compare-and-swap, so the guard is probabilistic under very high
  concurrency; combine with D1 `INSERT OR IGNORE` for hard uniqueness guarantees.
- KV TTL is set at write time in seconds; you cannot extend it without a re-write.

---

## Fingerprint Computation

```typescript
// src/lib/fingerprint.ts
import { createHash } from 'node:crypto';  // available in Workers via compatibility flag

/**
 * Produce a deterministic hex fingerprint from any serialisable payload.
 * Normalise before hashing so that field-order differences collapse.
 */
export function fingerprintOf(payload: unknown): string {
  const normalised = JSON.stringify(payload, Object.keys(payload as object).sort());
  return createHash('sha256').update(normalised).digest('hex').slice(0, 40);
}

// Alternative — no crypto flag needed, uses SubtleCrypto
export async function fingerprintOfAsync(payload: unknown): Promise<string> {
  const text = JSON.stringify(payload, Object.keys(payload as object).sort());
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 40);
}
```

---

## KV Deduplication Guard

```typescript
// src/lib/dedup-guard.ts

export interface DedupOptions {
  /** KV namespace bound to the Worker */
  kv: KVNamespace;
  /** Rolling window length in seconds — becomes the KV TTL */
  windowSeconds: number;
  /** Namespace prefix to avoid key collisions across event types */
  prefix?: string;
}

export type DedupResult =
  | { duplicate: false }
  | { duplicate: true; seenAt: string };

/**
 * Returns { duplicate: false } and records the fingerprint when unseen.
 * Returns { duplicate: true } when the fingerprint already exists in KV.
 */
export async function checkAndRecord(
  fingerprint: string,
  opts: DedupOptions,
): Promise<DedupResult> {
  const key = `${opts.prefix ?? 'dedup'}:${fingerprint}`;

  // Single read — fast path for the common case (new message)
  const existing = await opts.kv.getWithMetadata<{ seenAt: string }>(key, {
    type: 'text',
    cacheTtl: 60,
  });

  if (existing.value !== null) {
    return { duplicate: true, seenAt: existing.metadata?.seenAt ?? 'unknown' };
  }

  const seenAt = new Date().toISOString();
  // Write with TTL — automatically expires outside the window
  await opts.kv.put(key, '1', {
    expirationTtl: opts.windowSeconds,
    metadata: { seenAt },
  });

  return { duplicate: false };
}
```

---

## Queue Consumer Integration

```typescript
// src/handlers/email-dispatch-consumer.ts
import { fingerprintOfAsync } from '../lib/fingerprint';
import { checkAndRecord } from '../lib/dedup-guard';

export interface Env {
  DEDUP_KV: KVNamespace;
  DB: D1Database;
}

interface EmailJob {
  to: string;
  subject: string;
  body: string;
  templateId: string;
}

export default {
  async queue(batch: MessageBatch<EmailJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const fp = await fingerprintOfAsync(msg.body);

      const result = await checkAndRecord(fp, {
        kv: env.DEDUP_KV,
        windowSeconds: 86_400, // 24-hour dedup window
        prefix: 'email',
      });

      if (result.duplicate) {
        console.warn('Skipping duplicate email job', {
          fingerprint: fp,
          seenAt: result.seenAt,
          to: msg.body.to,
        });
        msg.ack(); // acknowledge so it does not re-queue
        continue;
      }

      await sendEmail(msg.body, env);
      msg.ack();
    }
  },
};

async function sendEmail(job: EmailJob, env: Env): Promise<void> {
  // actual email dispatch omitted for brevity
  await env.DB.prepare(
    'INSERT OR IGNORE INTO email_log (recipient, subject, sent_at) VALUES (?, ?, ?)',
  )
    .bind(job.to, job.subject, new Date().toISOString())
    .run();
}
```

---

## HTTP Handler Integration

```typescript
// src/handlers/webhook-receiver.ts
import { fingerprintOfAsync } from '../lib/fingerprint';
import { checkAndRecord } from '../lib/dedup-guard';

export interface Env {
  DEDUP_KV: KVNamespace;
}

export async function handleWebhook(req: Request, env: Env): Promise<Response> {
  const body = await req.json();

  const fp = await fingerprintOfAsync(body);
  const result = await checkAndRecord(fp, {
    kv: env.DEDUP_KV,
    windowSeconds: 300, // 5-minute window — tight, for webhooks
    prefix: 'webhook',
  });

  if (result.duplicate) {
    // Return 200 to silence the sender — they believe delivery succeeded
    return new Response(JSON.stringify({ status: 'duplicate', seenAt: result.seenAt }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  await processWebhook(body);

  return new Response(JSON.stringify({ status: 'accepted' }), {
    status: 202,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function processWebhook(body: unknown): Promise<void> {
  // business logic
}
```

---

## Sliding vs Fixed Window

```typescript
// Fixed window: TTL set from first-seen time — simple, tiny risk of aliasing at boundary
await kv.put(key, '1', { expirationTtl: windowSeconds });

// Sliding window: refresh TTL on each *non-duplicate* access within the window.
// Use when you want "no duplicate within N seconds of last occurrence"
// rather than "no duplicate within N seconds of first occurrence".
const existing2 = await kv.get(key);
if (existing2 === null) {
  await kv.put(key, '1', { expirationTtl: windowSeconds });
} else {
  // Refresh TTL — sliding
  await kv.put(key, '1', { expirationTtl: windowSeconds });
  return { duplicate: true };
}
```

---

## Anti-patterns

- **Hashing only the message ID** — IDs can be reused by callers after a deletion; hash
  the full payload or at minimum `(id, type, timestamp)`.
- **Using KV as the only guard at high concurrency** — KV is eventually consistent;
  under burst traffic two reads can both miss before the write propagates.  Back it with
  a D1 `INSERT OR IGNORE` on a unique column for hard dedup.
- **Omitting TTL** — a fingerprint stored forever bloats the namespace and incurs rising
  KV operation costs; always set `expirationTtl`.
- **Silent drops without logging** — duplicate rejection must be observable; log the
  fingerprint and original message metadata for replay audits.
- **Returning 4xx to the sender on duplicate** — this causes the sender to retry with
  the same payload, defeating the pattern.  Return 200/202.

---

## Gotchas

- **KV eventual consistency window** is typically < 60 s globally but is not guaranteed;
  within that window a duplicate message arriving at a different edge node can slip
  through.
- **Sort order of JSON keys** matters for deterministic fingerprinting — always sort keys
  before serialisation; JavaScript `JSON.stringify` does not guarantee order.
- **`node:crypto` requires** the `nodejs_compat` compatibility flag in `wrangler.toml`.
  Use `crypto.subtle` (available natively) when you cannot enable that flag.
- **KV `cacheTtl`** on reads reduces KV operation cost but means a very recent write
  may not be visible for up to `cacheTtl` seconds; set it lower than your window.
- **Large payloads**: hashing the full body of a 10 MB R2 object upload is wasteful;
  instead hash a compound key of `(bucket, key, etag)`.

---

## Verification

```typescript
// test/dedup-guard.test.ts
import { describe, it, expect, vi } from 'vitest';
import { checkAndRecord } from '../src/lib/dedup-guard';

describe('checkAndRecord', () => {
  const makeKv = () => {
    const store = new Map<string, string>();
    return {
      getWithMetadata: vi.fn(async (key: string) => ({
        value: store.get(key) ?? null,
        metadata: null,
      })),
      put: vi.fn(async (key: string, value: string) => {
        store.set(key, value);
      }),
    } as unknown as KVNamespace;
  };

  it('returns duplicate=false for first occurrence and records fingerprint', async () => {
    const kv = makeKv();
    const result = await checkAndRecord('abc123', { kv, windowSeconds: 60 });
    expect(result.duplicate).toBe(false);
    expect(kv.put).toHaveBeenCalledOnce();
  });

  it('returns duplicate=true for second call with same fingerprint', async () => {
    const kv = makeKv();
    await checkAndRecord('abc123', { kv, windowSeconds: 60 });
    // Simulate KV propagation — override the mock to return the value
    (kv.getWithMetadata as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      value: '1',
      metadata: { seenAt: '2026-08-23T00:00:00Z' },
    });
    const result = await checkAndRecord('abc123', { kv, windowSeconds: 60 });
    expect(result.duplicate).toBe(true);
  });
});
```

---

## Related

- `idempotency-key-pattern-workers-d1.md` — caller-supplied idempotency tokens
- `inbox-pattern-idempotent-consumption.md` — inbox table dedup in D1
- `dead-letter-queue-pattern.md` — handling messages that fail after dedup passes
- `exponential-backoff-jitter-workers.md` — retry strategy that pairs with dedup

---

## Sources

- Cloudflare KV docs — `expirationTtl` and `cacheTtl` semantics
  https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- Web Crypto API — `crypto.subtle.digest`
  https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
- Idempotency & deduplication in distributed systems — Martin Kleppmann, DDIA ch. 11
