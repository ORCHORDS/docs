# Event-Driven Saga with Compensation using Workers Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a multi-step distributed workflow — order placement, payment, fulfillment — where each step may fail and requires undoing prior steps to keep the system consistent. A choreography-based saga using Cloudflare Queues lets each step publish the next domain event, or a compensation event on failure, without a central orchestrator that becomes a bottleneck.

---

## Context

Each saga step is an independent Queue consumer Worker. `order.created` triggers the payment step; `payment.completed` triggers fulfillment; `fulfillment.failed` triggers compensation (refund + stock restore). Every step appends a row to a D1 `saga_log` table, giving you a full audit trail and an idempotency key to guard against duplicate Queue deliveries. Compensation events flow through the same Queue infrastructure, allowing you to retry compensations with the same at-least-once guarantees as forward steps.

---

## Schema — D1 Saga Log

```sql
CREATE TABLE IF NOT EXISTS saga_log (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  saga_id        TEXT    NOT NULL,
  step           TEXT    NOT NULL,  -- e.g. 'payment', 'fulfillment', 'refund'
  status         TEXT    NOT NULL,  -- 'started' | 'completed' | 'failed' | 'compensated'
  idempotency_key TEXT   NOT NULL UNIQUE,
  payload        TEXT,
  created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_saga_log_saga_id
  ON saga_log (saga_id);
```

---

## Wrangler Config

```toml
[[d1_databases]]
binding       = "DB"
database_name = "app-db"
database_id   = "<your-d1-database-id>"

[[queues.producers]]
binding    = "SAGA_BUS"
queue_name = "saga-events"

[[queues.consumers]]
queue             = "saga-events"
max_batch_size    = 5
max_batch_timeout = 3
```

---

## Implementation — Event Types and Helpers

```typescript
// saga-types.ts
export type SagaEventType =
  | 'order.created'
  | 'payment.completed'
  | 'payment.failed'
  | 'fulfillment.completed'
  | 'fulfillment.failed'
  | 'refund.completed'
  | 'stock.restored';

export interface SagaEvent {
  type:           SagaEventType;
  sagaId:         string;    // correlates all steps for one order
  idempotencyKey: string;    // step-scoped unique key for dedup
  payload:        Record<string, unknown>;
  occurredAt:     string;    // ISO-8601
}

export interface Env {
  DB:       D1Database;
  SAGA_BUS: Queue<SagaEvent>;
}

// Appends a log row; returns false if the idempotency key already exists (duplicate delivery)
export async function logStep(
  db: D1Database,
  sagaId: string,
  step: string,
  status: string,
  idempotencyKey: string,
  payload?: unknown
): Promise<boolean> {
  const result = await db.prepare(
    `INSERT OR IGNORE INTO saga_log
       (saga_id, step, status, idempotency_key, payload)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(sagaId, step, status, idempotencyKey, payload ? JSON.stringify(payload) : null)
    .run();

  return (result.meta.changes ?? 0) > 0; // false = duplicate, skip processing
}
```

---

## Implementation — Saga Consumer Worker

```typescript
// saga-worker.ts
import { SagaEvent, Env, logStep } from './saga-types';
import { v4 as uuid } from 'uuid';

export default {
  async queue(batch: MessageBatch<SagaEvent>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const event = message.body;
      try {
        await handleEvent(event, env);
        message.ack();
      } catch (err) {
        console.error(`Saga step failed for event ${event.type} sagaId=${event.sagaId}:`, err);
        message.retry(); // Queue will retry with back-off
      }
    }
  },
};

async function handleEvent(event: SagaEvent, env: Env): Promise<void> {
  const { type, sagaId, idempotencyKey, payload } = event;

  switch (type) {
    case 'order.created':          return handleOrderCreated(sagaId, idempotencyKey, payload, env);
    case 'payment.completed':      return handlePaymentCompleted(sagaId, idempotencyKey, payload, env);
    case 'payment.failed':         return handlePaymentFailed(sagaId, idempotencyKey, payload, env);
    case 'fulfillment.failed':     return handleFulfillmentFailed(sagaId, idempotencyKey, payload, env);
    case 'fulfillment.completed':  return handleFulfillmentCompleted(sagaId, idempotencyKey, payload, env);
    default:
      console.warn(`Unhandled saga event: ${type}`);
  }
}

// Step 1: reserve payment
async function handleOrderCreated(
  sagaId: string,
  ikey: string,
  payload: Record<string, unknown>,
  env: Env
): Promise<void> {
  const inserted = await logStep(env.DB, sagaId, 'payment', 'started', ikey, payload);
  if (!inserted) return; // duplicate delivery — skip

  // Call payment service
  const paymentOk = await chargePayment(payload.totalCents as number);

  const nextType: SagaEvent['type'] = paymentOk ? 'payment.completed' : 'payment.failed';
  const nextKey   = uuid();

  await logStep(env.DB, sagaId, 'payment', paymentOk ? 'completed' : 'failed', nextKey + '-log');

  await env.SAGA_BUS.send({
    type:           nextType,
    sagaId,
    idempotencyKey: nextKey,
    payload,
    occurredAt:     new Date().toISOString(),
  });
}

// Step 2: trigger fulfillment
async function handlePaymentCompleted(
  sagaId: string,
  ikey: string,
  payload: Record<string, unknown>,
  env: Env
): Promise<void> {
  const inserted = await logStep(env.DB, sagaId, 'fulfillment', 'started', ikey, payload);
  if (!inserted) return;

  const fulfilled = await dispatchFulfillment(payload.orderId as string);
  const nextType: SagaEvent['type'] = fulfilled ? 'fulfillment.completed' : 'fulfillment.failed';
  const nextKey = uuid();

  await logStep(env.DB, sagaId, 'fulfillment', fulfilled ? 'completed' : 'failed', nextKey + '-log');

  await env.SAGA_BUS.send({
    type:           nextType,
    sagaId,
    idempotencyKey: nextKey,
    payload,
    occurredAt:     new Date().toISOString(),
  });
}

// Compensation step A: issue refund
async function handleFulfillmentFailed(
  sagaId: string,
  ikey: string,
  payload: Record<string, unknown>,
  env: Env
): Promise<void> {
  const inserted = await logStep(env.DB, sagaId, 'refund', 'started', ikey, payload);
  if (!inserted) return;

  await issueRefund(payload.totalCents as number);
  await restoreStock(payload.orderId as string);

  await logStep(env.DB, sagaId, 'refund', 'compensated', ikey + '-done');

  await env.SAGA_BUS.send({
    type:           'refund.completed',
    sagaId,
    idempotencyKey: uuid(),
    payload,
    occurredAt:     new Date().toISOString(),
  });
}

async function handlePaymentFailed(
  sagaId: string,
  ikey: string,
  payload: Record<string, unknown>,
  env: Env
): Promise<void> {
  await logStep(env.DB, sagaId, 'payment', 'compensated', ikey + '-comp', payload);
  // No prior steps to compensate — order never advanced
  console.log(`Saga ${sagaId}: payment failed, no compensation needed`);
}

async function handleFulfillmentCompleted(
  sagaId: string,
  ikey: string,
  _payload: Record<string, unknown>,
  env: Env
): Promise<void> {
  await logStep(env.DB, sagaId, 'fulfillment', 'completed', ikey + '-final');
  console.log(`Saga ${sagaId}: fully complete`);
}

// --- Stub service calls — replace with real implementations ---
async function chargePayment(_cents: number):      Promise<boolean> { return Math.random() > 0.1; }
async function dispatchFulfillment(_orderId: string): Promise<boolean> { return Math.random() > 0.2; }
async function issueRefund(_cents: number):         Promise<void>    { /* call payment API */ }
async function restoreStock(_orderId: string):      Promise<void>    { /* call inventory API */ }
```

---

## Anti-patterns

- **Missing idempotency keys** — Queues deliver at-least-once; without deduplication in `saga_log`, a retry can double-charge or double-refund.
- **Throwing inside the queue handler without retrying** — Catching all errors and calling `message.ack()` silently swallows failures; only ack after confirmed success.
- **Saga state held purely in memory** — Any Worker restart loses in-flight saga context; always persist state to D1.
- **Long saga chains in a single Worker** — Keeps the Worker alive for the full chain duration and wastes CPU time; break each step into a separate Queue message.

---

## Gotchas

- Queue consumer Workers share the same `queue` setting; if you have multiple saga types on one queue, route by `event.type` inside a single consumer — or use separate queues per domain.
- `INSERT OR IGNORE` returns `changes = 0` on a duplicate; always check this before doing side-effecting work.
- Compensation is not a rollback — it is a new forward action (refund, stock restore) that must itself be idempotent.
- Dead-letter queues are not yet a native Cloudflare feature (as of 2026-08); implement your own DLQ by writing failed messages to D1 after `max_retries` exhausted.

---

## Verification

```bash
# Apply schema
wrangler d1 execute app-db --file=schema.sql

# Seed an order.created event manually via wrangler tail + queue send
wrangler queues send saga-events \
  --message '{"type":"order.created","sagaId":"saga-001","idempotencyKey":"ik-001","payload":{"orderId":"o-1","totalCents":4999},"occurredAt":"2026-08-24T00:00:00Z"}'

# Watch the log fill in
wrangler d1 execute app-db \
  --command "SELECT saga_id, step, status, created_at FROM saga_log ORDER BY id;"

# Inspect a compensation scenario (fulfillment always fails at rate 0.2)
wrangler d1 execute app-db \
  --command "SELECT * FROM saga_log WHERE status='compensated';"
```

---

## Related

- `outbox-pattern-workers-d1-queues.md`
- `circuit-breaker-workers-durable-objects.md`
- `scatter-gather-workers-queues.md`

---

## Sources

- Cloudflare Queues Consumer API — https://developers.cloudflare.com/queues/configuration/javascript-apis/#consumer
- Saga Pattern (microservices.io) — https://microservices.io/patterns/data/saga.html
- Cloudflare D1 INSERT OR IGNORE — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
