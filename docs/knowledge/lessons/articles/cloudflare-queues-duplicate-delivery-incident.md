# Cloudflare Queues Duplicate Delivery Incident

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A payment confirmation worker consumed messages from a Cloudflare Queue. During a
platform-side network partition lasting ~12 minutes, the Queue broker re-delivered a
batch of 340 messages that the consumer Worker had already fully processed and implicitly
acknowledged. Because the consumer did not guard against duplicate delivery, 340 payment
confirmation emails were sent twice and 62 loyalty-point ledger entries were doubled.
The bug was discovered by a user who noticed a doubled points balance, not by any
internal alerting.

## Context

Cloudflare Queues guarantees **at-least-once** delivery, not exactly-once. A message is
considered acknowledged only after the consumer Worker returns a successful response (or
calls `msg.ack()` on individual messages) and the acknowledgement reaches the Queue
broker. If a network issue prevents the broker from receiving the acknowledgement — even
after the consumer has fully processed the message — the broker re-delivers the message
after the visibility timeout expires. This is standard behaviour for distributed message
queues (SQS, Pub/Sub, Kafka all share the same semantic). Every consumer Worker on
Cloudflare Queues must be idempotent by design.

## Idempotency Key Stored in D1

The most reliable deduplication strategy is a database write that is atomic with the
business action. Use the Queue message ID as an idempotency key stored in D1.

```typescript
// src/payment-consumer.ts
interface PaymentMessage {
  orderId: string;
  userId: string;
  amountCents: number;
}

export default {
  async queue(batch: MessageBatch<PaymentMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processPaymentOnce(env, msg.id, msg.body);
        msg.ack();
      } catch (err) {
        console.error('payment processing error', { msgId: msg.id, err });
        msg.retry();
      }
    }
  },
} satisfies ExportedHandler<Env>;

async function processPaymentOnce(
  env: Env,
  msgId: string,
  payment: PaymentMessage,
): Promise<void> {
  // INSERT OR IGNORE is the atomic guard — if msgId already exists, the INSERT is a
  // no-op and `changes` is 0, so we skip downstream effects.
  const result = await env.DB.prepare(
    'INSERT OR IGNORE INTO processed_queue_messages (msg_id, processed_at) VALUES (?1, unixepoch())',
  )
    .bind(msgId)
    .run();

  if ((result.meta.changes ?? 0) === 0) {
    // Duplicate delivery — already processed
    return;
  }

  await sendConfirmationEmail(env, payment);
  await creditLoyaltyPoints(env, payment);
}
```

## Batch-Level Deduplication With Bulk Insert

When processing large batches, a per-message SELECT is expensive. Bulk-insert all message
IDs in one batch call and derive the set of new (unprocessed) IDs from the result.

```typescript
// src/lib/dedup.ts
export async function filterNewMessages<T extends { id: string }>(
  db: D1Database,
  messages: T[],
): Promise<T[]> {
  if (messages.length === 0) return [];

  const stmts = messages.map((m) =>
    db.prepare(
      'INSERT OR IGNORE INTO processed_queue_messages (msg_id, processed_at) VALUES (?1, unixepoch())',
    ).bind(m.id),
  );

  const results = await db.batch(stmts);
  return messages.filter((_, i) => (results[i].meta.changes ?? 0) > 0);
}
```

## KV-Backed Short-Window Dedup for High-Throughput Paths

For latency-sensitive consumers where D1 write latency is unacceptable, use KV with a
TTL equal to the maximum re-delivery window. This is a probabilistic guard (KV is
eventually consistent) and must be paired with the D1 guard for financial operations.

```typescript
// src/lib/kv-dedup.ts
const KV_DEDUP_TTL_SECONDS = 600; // longer than queue visibility timeout

export async function isAlreadyProcessed(
  kv: KVNamespace,
  msgId: string,
): Promise<boolean> {
  return (await kv.get(`dedup:${msgId}`)) !== null;
}

export async function markProcessed(kv: KVNamespace, msgId: string): Promise<void> {
  await kv.put(`dedup:${msgId}`, '1', { expirationTtl: KV_DEDUP_TTL_SECONDS });
}
```

## Alert on Duplicate Delivery Events

Track duplicate deliveries explicitly so you can distinguish a consumer bug (same logic
running twice) from a platform re-delivery (normal at-least-once behaviour).

```typescript
// src/payment-consumer.ts (metric emission)
async function processPaymentOnce(
  env: Env,
  msgId: string,
  payment: PaymentMessage,
): Promise<void> {
  const result = await env.DB.prepare(
    'INSERT OR IGNORE INTO processed_queue_messages (msg_id, processed_at) VALUES (?1, unixepoch())',
  )
    .bind(msgId)
    .run();

  const isDuplicate = (result.meta.changes ?? 0) === 0;
  if (isDuplicate) {
    env.ANALYTICS?.writeDataPoint({
      blobs: [msgId, payment.orderId],
      doubles: [1],
      indexes: ['queue_duplicate_delivery'],
    });
    return;
  }

  await sendConfirmationEmail(env, payment);
  await creditLoyaltyPoints(env, payment);
}
```

## Exponential Backoff on Retry With Jitter

Consumer errors cause `msg.retry()`. Without a backoff strategy, all retried messages
hit the consumer simultaneously on re-delivery, creating a thundering-herd pattern.
Use `msg.retry({ delaySeconds })` to spread retries.

```typescript
// src/lib/retry-with-backoff.ts
export function retryDelay(attempt: number): number {
  const base = 5; // seconds
  const cap = 300; // 5 minutes max
  const exp = Math.min(base * 2 ** attempt, cap);
  const jitter = Math.random() * exp * 0.25;
  return Math.floor(exp + jitter);
}

// In consumer:
// msg.retry({ delaySeconds: retryDelay(msg.attempts - 1) });
```

## Anti-patterns

- Assuming Queue delivery is exactly-once — it is not; every consumer must be idempotent.
- Using only a timestamp as a uniqueness key — a re-delivered message has the same `id`
  as the original, but using `Date.now()` would generate a new key and bypass dedup.
- Acking the full batch (`batch.ackAll()`) when only some messages were successfully
  processed — this loses the un-processed messages permanently.
- Relying solely on KV for deduplication of financial operations — KV is eventually
  consistent and a write may not be visible to another PoP within the re-delivery window.

## Gotchas

- `msg.id` is stable across re-deliveries of the same message; it is the correct
  idempotency key. Do not use message body fields as the key unless they are globally
  unique and immutable.
- `batch.ackAll()` and `batch.retryAll()` are conveniences; when mixed processing
  outcomes are possible, use per-message `msg.ack()` / `msg.retry()`.
- The D1 `INSERT OR IGNORE` guard requires a UNIQUE constraint on `msg_id`; ensure the
  migration creates this constraint before deploying the consumer.
- `processed_queue_messages` grows unboundedly; add a TTL cleanup cron to delete rows
  older than the maximum re-delivery window (typically 4 hours for Cloudflare Queues).

## Verification

1. Unit test: send the same message ID to the consumer twice; assert
   `sendConfirmationEmail` and `creditLoyaltyPoints` are each called exactly once.
2. Integration test in staging: manually re-deliver a batch via the Cloudflare dashboard
   retry; confirm the `queue_duplicate_delivery` Analytics Engine metric increments.
3. Confirm `processed_queue_messages` has a UNIQUE constraint by attempting a raw
   duplicate INSERT in D1 and verifying the constraint violation.
4. Load test: send 1,000 messages with 10% duplicates; assert downstream effects match
   the count of unique message IDs, not total messages.

## Related

- `queue-consumers-must-be-idempotent.md`
- `queues-consumer-scaling-backpressure-lesson.md`
- `retry-storm-queue-poison-message.md`
- `idempotency-keys-for-all-payment-calls.md`
- `cloudflare-queues-vs-traditional-message-queues.md`

## Sources

- Cloudflare Queues documentation — at-least-once delivery guarantees (2026)
- AWS SQS documentation — visibility timeout and at-least-once semantics (reference)
- Internal postmortem: example.com duplicate payment confirmation incident, Q1 2026
- Cloudflare Blog: "Cloudflare Queues: open beta" (2023)
