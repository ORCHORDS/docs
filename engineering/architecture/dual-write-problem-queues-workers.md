# Dual-Write Problem: Solving It with Workers Queues and D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

The dual-write problem occurs whenever a single operation must update two separate systems atomically—for example, writing a row to D1 and publishing a message to a Queue. If the D1 write succeeds but the Queue send fails (or vice versa), the two systems diverge silently. Retrying the whole operation without idempotency guards causes duplicates. The result is a class of bugs that is difficult to reproduce, dangerous in financial or inventory systems, and nearly impossible to detect without explicit consistency monitoring.

In Cloudflare Workers the problem appears most often when teams write to D1 (the source of truth) and then call `env.QUEUE.send()` to notify downstream services. Network timeouts, Worker CPU limits, or uncaught exceptions between the two steps are enough to create the divergence.

## Context

Cloudflare D1 supports multi-statement transactions via `db.batch()` and `db.transaction()`. Cloudflare Queues guarantees at-least-once delivery with automatic retries but does not participate in D1 transactions. The two systems have no shared transaction coordinator, so you cannot commit to both atomically using standard primitives.

The canonical solution is the **transactional outbox pattern**: instead of writing to the Queue directly, the Worker writes an outbox record inside the same D1 transaction as the business entity update. A separate polling Worker (or Durable Object alarm) reads undelivered outbox rows, sends them to the Queue, and marks them delivered—all with idempotency guards. This moves the dual-write problem from "D1 + Queue" to "D1 only," where atomicity is achievable.

This article focuses specifically on the dual-write failure modes and the outbox implementation that eliminates them. For the transactional outbox in isolation see `outbox-pattern.md`.

## Failure Modes Without the Outbox

Understanding the specific failure modes makes the solution legible:

```typescript
// DANGEROUS: Dual-write without outbox
export async function createOrder(env: Env, order: OrderInput): Promise<string> {
  const orderId = crypto.randomUUID();

  // Step 1: Write to D1
  await env.DB.prepare(
    'INSERT INTO orders (id, user_id, total, status) VALUES (?, ?, ?, ?)'
  ).bind(orderId, order.userId, order.total, 'pending').run();

  // Step 2: Publish to Queue
  // FAILURE WINDOW: Worker CPU limit hit, network timeout, or exception here
  // leaves D1 written but Queue empty. Downstream never processes the order.
  await env.ORDER_QUEUE.send({ type: 'OrderCreated', orderId, total: order.total });

  return orderId;
}
```

Failure scenarios in the window between Step 1 and Step 2:
- Worker hits the 50 ms CPU time limit on the free plan
- Queue send times out (transient Cloudflare network issue)
- An unhandled exception in intervening logic
- The Worker instance is evicted between the two awaits

## Outbox Table and Atomic Write

Replace the direct Queue send with an outbox row written in the same D1 batch as the business entity:

```typescript
// src/outbox/writer.ts
export interface OutboxEvent {
  id: string;
  aggregate_type: string;
  aggregate_id: string;
  event_type: string;
  payload: string;  // JSON string
  created_at: string;
  delivered_at: string | null;
  attempts: number;
}

export async function createOrderWithOutbox(
  env: Env,
  order: OrderInput
): Promise<string> {
  const orderId = crypto.randomUUID();
  const outboxId = crypto.randomUUID();
  const now = new Date().toISOString();

  const payload = JSON.stringify({
    type: 'OrderCreated',
    orderId,
    userId: order.userId,
    total: order.total,
    occurredAt: now,
  });

  // Single D1 batch — both rows commit or both roll back
  await env.DB.batch([
    env.DB.prepare(
      'INSERT INTO orders (id, user_id, total, status, created_at) VALUES (?, ?, ?, ?, ?)'
    ).bind(orderId, order.userId, order.total, 'pending', now),

    env.DB.prepare(
      `INSERT INTO outbox_events
         (id, aggregate_type, aggregate_id, event_type, payload, created_at, delivered_at, attempts)
       VALUES (?, ?, ?, ?, ?, ?, NULL, 0)`
    ).bind(outboxId, 'order', orderId, 'OrderCreated', payload, now),
  ]);

  // No Queue send here — the relay Worker handles that independently
  return orderId;
}
```

The `orders` and `outbox_events` tables are updated in a single `batch()` call, which D1 executes transactionally. If either statement fails, neither is committed.

## Outbox Relay Worker (Durable Object with Alarm)

A Durable Object polls the outbox table on a scheduled alarm, sends undelivered rows to the Queue, and marks them delivered—all idempotently.

```typescript
// src/outbox/relay.ts
import { DurableObject } from 'cloudflare:workers';

export class OutboxRelay extends DurableObject {
  private readonly POLL_INTERVAL_MS = 5_000;
  private readonly BATCH_SIZE = 50;

  async fetch(_request: Request): Promise<Response> {
    // Triggered by the host Worker to start the relay if not already running
    await this.ensureAlarmScheduled();
    return new Response('Relay running');
  }

  async alarm(): Promise<void> {
    await this.drainOutbox();
    // Reschedule for next poll
    await this.ctx.storage.setAlarm(Date.now() + this.POLL_INTERVAL_MS);
  }

  private async ensureAlarmScheduled(): Promise<void> {
    const existing = await this.ctx.storage.getAlarm();
    if (existing === null) {
      await this.ctx.storage.setAlarm(Date.now() + this.POLL_INTERVAL_MS);
    }
  }

  private async drainOutbox(): Promise<void> {
    const env = this.env as Env;

    // Fetch oldest undelivered events
    const { results } = await env.DB.prepare(
      `SELECT * FROM outbox_events
       WHERE delivered_at IS NULL AND attempts < 5
       ORDER BY created_at ASC
       LIMIT ?`
    ).bind(this.BATCH_SIZE).all<OutboxEvent>();

    if (!results.length) return;

    for (const event of results) {
      try {
        // Idempotent: if the Queue already received this (duplicate relay),
        // the consumer uses event.id as a deduplication key
        await env.ORDER_QUEUE.send(
          { ...JSON.parse(event.payload), outboxId: event.id },
          { contentType: 'json' }
        );

        await env.DB.prepare(
          'UPDATE outbox_events SET delivered_at = ?, attempts = attempts + 1 WHERE id = ?'
        ).bind(new Date().toISOString(), event.id).run();
      } catch (err) {
        console.error(`Failed to relay outbox event ${event.id}:`, err);
        await env.DB.prepare(
          'UPDATE outbox_events SET attempts = attempts + 1 WHERE id = ?'
        ).bind(event.id).run();
      }
    }
  }
}
```

## Consumer Idempotency Guard

Because the relay uses at-least-once delivery, consumers may receive the same event more than once. An idempotency table in D1 prevents duplicate processing:

```typescript
// src/queue/consumer.ts
export default {
  async queue(batch: MessageBatch<RelayedEvent>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const event = message.body;

      // Check idempotency
      const existing = await env.DB.prepare(
        'SELECT 1 FROM processed_events WHERE outbox_id = ?'
      ).bind(event.outboxId).first();

      if (existing) {
        message.ack();  // Already processed — safe to discard
        continue;
      }

      try {
        await processEvent(event, env);

        // Mark as processed — this write is in a separate D1 transaction
        await env.DB.prepare(
          'INSERT INTO processed_events (outbox_id, processed_at) VALUES (?, ?)'
        ).bind(event.outboxId, new Date().toISOString()).run();

        message.ack();
      } catch (err) {
        console.error('Consumer error:', err);
        message.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function processEvent(event: RelayedEvent, env: Env): Promise<void> {
  if (event.type === 'OrderCreated') {
    await env.DB.prepare(
      'INSERT INTO inventory_reservations (order_id, status) VALUES (?, ?)'
    ).bind(event.orderId, 'pending').run();
  }
}

interface RelayedEvent {
  type: string;
  outboxId: string;
  orderId: string;

}
```

## Schema Reference

```sql
-- D1 migration
CREATE TABLE IF NOT EXISTS outbox_events (
  id             TEXT PRIMARY KEY,
  aggregate_type TEXT NOT NULL,
  aggregate_id   TEXT NOT NULL,
  event_type     TEXT NOT NULL,
  payload        TEXT NOT NULL,
  created_at     TEXT NOT NULL,
  delivered_at   TEXT,
  attempts       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_undelivered
  ON outbox_events (created_at)
  WHERE delivered_at IS NULL AND attempts < 5;

CREATE TABLE IF NOT EXISTS processed_events (
  outbox_id    TEXT PRIMARY KEY,
  processed_at TEXT NOT NULL
);
```

## Anti-patterns

- Writing to the Queue directly after a D1 write without an outbox—this is the dual-write problem itself.
- Using a `try/catch` around the Queue send and retrying in the same Worker request—CPU limits and Worker eviction make this unreliable; move retry responsibility to a separate process.
- Polling the outbox on a fixed cron (`scheduled` Worker) with a 1-minute interval—5-second Durable Object alarms reduce event latency dramatically for time-sensitive workflows.
- Not bounding the relay `attempts` column—a permanently failing Queue send will loop indefinitely and fill the outbox table.
- Deleting processed outbox rows immediately—retain them for at least 24 hours to support audit and replay use cases.

## Gotchas

- D1 `batch()` does not support cross-table foreign key constraints within the batch; add them as separate D1 migrations if needed.
- The Durable Object alarm fires at the region-local instance; if you use `idFromName('outbox-relay')` it always targets the same DO instance globally. Use a routing strategy based on `aggregate_type` or shard ID to spread relay load across multiple DO instances.
- D1's partial index syntax (`WHERE delivered_at IS NULL`) requires SQLite 3.8.9+. D1 is built on SQLite and supports it, but verify with a simple `EXPLAIN QUERY PLAN` that the index is being used.
- The relay Worker's `drainOutbox` method is not itself atomic with respect to the Queue send. If the relay crashes after sending but before marking `delivered_at`, the event will be resent. Consumer idempotency is mandatory, not optional.
- Large `payload` TEXT values (>8 KB) in D1 perform well but inflate the outbox table scan. Consider storing payloads in R2 and keeping only the R2 key in the outbox row (claim-check pattern).

## Verification

1. Write an order through `createOrderWithOutbox()` and immediately kill the Worker (simulate with an early `throw`). Confirm the outbox row exists in D1 and the order row exists, but the Queue has no message.
2. Start the `OutboxRelay` Durable Object and wait for the next alarm (5 s). Confirm the Queue receives the message and `delivered_at` is set on the outbox row.
3. Re-send the same outbox event to the Queue (simulate relay duplicate) and confirm the consumer acks it without calling `processEvent` again.
4. Set `attempts` to 5 on an outbox row and confirm the relay skips it and does not increment further.
5. Run `SELECT * FROM outbox_events WHERE delivered_at IS NULL` after a normal flow—expect zero rows within 10 seconds of the write.

## Related

- `outbox-pattern.md` — foundational transactional outbox pattern
- `at-least-once-delivery.md` — delivery guarantees and retry semantics
- `idempotency-design.md` — idempotency key patterns for safe retries
- `durable-object-alarm-api-scheduled-retry.md` — Durable Object alarm scheduling

## Sources

- "Microservices Patterns" by Chris Richardson (Outbox pattern chapter): https://microservices.io/patterns/data/transactional-outbox.html
- Cloudflare D1 batch operations: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Queues at-least-once delivery guarantees: https://developers.cloudflare.com/queues/reference/delivery-guarantees/
