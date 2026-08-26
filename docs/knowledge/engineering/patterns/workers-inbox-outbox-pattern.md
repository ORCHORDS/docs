# Inbox-Outbox Pattern for Reliable Messaging with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You write a record to D1 and then send a message to an external system (email, Slack, analytics pipeline). If the Worker crashes between the write and the send, the external system never learns about the change. Conversely, if the send succeeds but the write fails, the external system has a record the database does not. You need at-least-once delivery with idempotent processing at the receiver.

---

## Context

The outbox pattern decouples the state change from its side effects. The domain write and the outbox entry are committed in a **single D1 transaction**. A separate process (here, a Workers Queue consumer) reads the outbox, delivers events to external systems, and marks entries as delivered — all without holding a database lock. The inbox pattern mirrors this on the receiver side: before processing, insert an idempotency key; skip if already present.

Cloudflare Workers Queues provide at-least-once delivery, which aligns perfectly with this model. The queue consumer is free to fail and retry without risk of message loss, and the inbox deduplication handles duplicates.

---

## Solution

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
  EVENT_QUEUE: Queue<OutboxMessage>;
  EXTERNAL_WEBHOOK_URL: string;
}

export interface OutboxMessage {
  eventId: string;
  aggregateType: string;
  aggregateId: string;
  eventType: string;
  payload: unknown;
  occurredAt: string; // ISO-8601
  sequence: number;   // monotonic per aggregate for ordering
}

// src/schema.sql — run once via wrangler d1 execute
// CREATE TABLE IF NOT EXISTS outbox (
//   event_id      TEXT PRIMARY KEY,
//   aggregate_type TEXT NOT NULL,
//   aggregate_id  TEXT NOT NULL,
//   event_type    TEXT NOT NULL,
//   payload       TEXT NOT NULL,
//   occurred_at   TEXT NOT NULL,
//   sequence      INTEGER NOT NULL,
//   delivered_at  TEXT
// );
//
// CREATE TABLE IF NOT EXISTS inbox (
//   event_id      TEXT PRIMARY KEY,
//   received_at   TEXT NOT NULL,
//   processed_at  TEXT
// );
//
// CREATE INDEX IF NOT EXISTS idx_outbox_undelivered
//   ON outbox(delivered_at) WHERE delivered_at IS NULL;
//
// CREATE INDEX IF NOT EXISTS idx_outbox_aggregate_sequence
//   ON outbox(aggregate_id, sequence);

// src/domain.ts
import { Env, OutboxMessage } from './types';

/**
 * Save a new order AND write its creation event to the outbox
 * in a single D1 transaction — no two-phase commit required.
 */
export async function createOrder(
  env: Env,
  orderId: string,
  userId: string,
  items: { sku: string; qty: number }[],
): Promise<void> {
  const eventId = crypto.randomUUID();
  const occurredAt = new Date().toISOString();

  // Get the current max sequence for this aggregate to maintain ordering
  const seqRow = await env.DB
    .prepare('SELECT COALESCE(MAX(sequence), 0) AS seq FROM outbox WHERE aggregate_id = ?')
    .bind(orderId)
    .first<{ seq: number }>();
  const sequence = (seqRow?.seq ?? 0) + 1;

  const payload = JSON.stringify({ userId, items });
  const eventPayload = JSON.stringify({ orderId, userId, items });

  await env.DB.batch([
    // 1. Write the domain entity
    env.DB.prepare(
      'INSERT INTO orders (order_id, user_id, payload, created_at) VALUES (?, ?, ?, ?)'
    ).bind(orderId, userId, payload, occurredAt),

    // 2. Write the outbox entry in the same transaction
    env.DB.prepare(`
      INSERT INTO outbox
        (event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at, sequence)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).bind(eventId, 'order', orderId, 'OrderCreated', eventPayload, occurredAt, sequence),
  ]);
}

// src/outbox-publisher.ts
import { Env, OutboxMessage } from './types';

/**
 * Scheduled Worker (or DO alarm) that polls the outbox and enqueues
 * undelivered events. Runs every minute via a cron trigger.
 */
export async function publishOutboxEvents(env: Env): Promise<void> {
  const { results } = await env.DB
    .prepare(`
      SELECT event_id, aggregate_type, aggregate_id, event_type,
             payload, occurred_at, sequence
      FROM outbox
      WHERE delivered_at IS NULL
      ORDER BY occurred_at ASC
      LIMIT 100
    `)
    .all<{
      event_id: string;
      aggregate_type: string;
      aggregate_id: string;
      event_type: string;
      payload: string;
      occurred_at: string;
      sequence: number;
    }>();

  if (!results.length) return;

  const messages: OutboxMessage[] = results.map((row) => ({
    eventId: row.event_id,
    aggregateType: row.aggregate_type,
    aggregateId: row.aggregate_id,
    eventType: row.event_type,
    payload: JSON.parse(row.payload),
    occurredAt: row.occurred_at,
    sequence: row.sequence,
  }));

  // Batch-enqueue to the Queue (max 100 per sendBatch call)
  await env.EVENT_QUEUE.sendBatch(
    messages.map((msg) => ({ body: msg }))
  );

  // Mark as delivered in outbox (idempotent even if queue already has them)
  const placeholders = messages.map(() => '?').join(', ');
  await env.DB
    .prepare(`UPDATE outbox SET delivered_at = ? WHERE event_id IN (${placeholders})`)
    .bind(new Date().toISOString(), ...messages.map((m) => m.eventId))
    .run();
}

// src/queue-consumer.ts
import { Env, OutboxMessage } from './types';

/**
 * Queue consumer: receives events from the queue and delivers them
 * to the external system with idempotent inbox deduplication.
 */
export default {
  async queue(
    batch: MessageBatch<OutboxMessage>,
    env: Env,
  ): Promise<void> {
    for (const message of batch.messages) {
      const event = message.body;

      try {
        const alreadyProcessed = await checkInbox(env, event.eventId);
        if (alreadyProcessed) {
          console.log(JSON.stringify({ event: 'inbox_duplicate', eventId: event.eventId }));
          message.ack();
          continue;
        }

        // Write inbox entry BEFORE processing — prevents double-processing
        // if the Worker crashes after delivery but before ack.
        await writeInbox(env, event.eventId);

        await deliverToExternalSystem(env, event);

        await markInboxProcessed(env, event.eventId);

        message.ack();

        console.log(JSON.stringify({
          event: 'event_delivered',
          eventId: event.eventId,
          eventType: event.eventType,
        }));
      } catch (err) {
        // Do NOT ack — the Queue will redeliver after the visibility timeout.
        // After max retries, the message goes to the dead letter queue.
        console.error(JSON.stringify({
          event: 'delivery_failed',
          eventId: event.eventId,
          error: String(err),
        }));
        message.retry();
      }
    }
  },
};

async function checkInbox(env: Env, eventId: string): Promise<boolean> {
  const row = await env.DB
    .prepare('SELECT event_id FROM inbox WHERE event_id = ?')
    .bind(eventId)
    .first();
  return row !== null;
}

async function writeInbox(env: Env, eventId: string): Promise<void> {
  await env.DB
    .prepare('INSERT OR IGNORE INTO inbox (event_id, received_at) VALUES (?, ?)')
    .bind(eventId, new Date().toISOString())
    .run();
}

async function markInboxProcessed(env: Env, eventId: string): Promise<void> {
  await env.DB
    .prepare('UPDATE inbox SET processed_at = ? WHERE event_id = ?')
    .bind(new Date().toISOString(), eventId)
    .run();
}

async function deliverToExternalSystem(
  env: Env,
  event: OutboxMessage,
): Promise<void> {
  const response = await fetch(env.EXTERNAL_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(event),
  });

  if (!response.ok) {
    throw new Error(`Webhook delivery failed: ${response.status}`);
  }
}
```

```jsonc
// wrangler.toml (relevant excerpt)
[[queues.producers]]
binding = "EVENT_QUEUE"
queue = "outbox-events"

[[queues.consumers]]
queue = "outbox-events"
max_batch_size = 100
max_batch_timeout = 5
max_retries = 5
dead_letter_queue = "outbox-events-dlq"

[triggers]
crons = ["* * * * *"] // Poll outbox every minute
```

---

## Implementation Details

**Atomic outbox write:** `DB.batch([domainWrite, outboxWrite])` wraps both statements in a single D1 transaction. If either fails, neither is committed — so the domain state and the outbox are always consistent.

**At-least-once delivery:** The Queue consumer may receive the same message multiple times (network failures, Worker restarts). The inbox table's `INSERT OR IGNORE` prevents double-processing based on `event_id`.

**Event ordering per aggregate:** The `sequence` column ensures that for a given `aggregate_id`, events can be sorted in the order they occurred. Consumers that care about ordering should sort by `(aggregate_id, sequence)` rather than `occurred_at` (wall clocks can skew).

**Dead letter handling:** After `max_retries` (5), the Queue moves the message to `outbox-events-dlq`. Monitor this queue with a separate consumer that alerts on arrival or writes to a dead_letters table for human review.

**Outbox cleanup:** Add a scheduled job to delete rows where `delivered_at < (NOW - 30 days)` to prevent unbounded table growth.

---

## Anti-patterns

- **Writing to the queue inside the D1 transaction.** `queue.send()` is async and cannot participate in a D1 transaction; calling it inside `batch()` will not give you atomicity.
- **Using `event.eventId` from the queue message as the D1 primary key without `INSERT OR IGNORE`.** A plain `INSERT` will throw a unique constraint error on redelivery and cause the message to be retried forever.
- **Polling the outbox on every request.** Run the outbox publisher on a cron trigger (every 1–5 minutes) rather than in the request path — polling D1 on each request adds latency and wastes D1 read units.
- **Deleting outbox rows immediately after enqueuing.** Keep rows until confirmed delivered so you can replay events if the queue consumer has a bug.

---

## Gotchas

- **D1 `batch()` is not a true ACID transaction in the SQL sense** — it runs statements serially in a single request and rolls back on error, but it does not support savepoints or manual `ROLLBACK`.
- **Queue message size limit is 128 KB.** If your event payload exceeds this, use the claim check pattern (`workers-claim-check-pattern.md`) to store the payload in R2 and enqueue only the reference.
- **`INSERT OR IGNORE` silently swallows constraint errors.** Verify your inbox deduplication by checking `changes()` if you need to distinguish insert from skip.
- **D1 is eventually consistent across read replicas.** The outbox publisher should query the primary (default in Workers) to avoid reading a stale replica that misses recent outbox rows.

---

## Verification

```bash
# Trigger order creation
curl -X POST https://your-worker.workers.dev/orders \
  -H 'Content-Type: application/json' \
  -d '{"userId": "u1", "items": [{"sku": "SKU-001", "qty": 2}]}'

# Check outbox (should show delivered_at NULL until cron runs)
wrangler d1 execute YOUR_DB --command \
  "SELECT event_id, event_type, delivered_at FROM outbox ORDER BY occurred_at DESC LIMIT 5;"

# After cron fires, delivered_at should be populated
# Check inbox for processed events
wrangler d1 execute YOUR_DB --command \
  "SELECT event_id, received_at, processed_at FROM inbox ORDER BY received_at DESC LIMIT 5;"

# Check dead letter queue (should be empty under normal conditions)
wrangler queues list
```

---

## Related

- `workers-claim-check-pattern.md` — handle payloads > 128 KB in queues
- `workers-compensating-transaction-pattern.md` — rollback saga steps when delivery fails
- Cloudflare Docs: [Workers Queues](https://developers.cloudflare.com/queues/)
- Cloudflare Docs: [D1 Database](https://developers.cloudflare.com/d1/)

---

## Sources

- Transactional Outbox pattern — microservices.io: https://microservices.io/patterns/data/transactional-outbox.html
- Idempotent Consumer pattern — microservices.io: https://microservices.io/patterns/communication-style/idempotent-consumer.html
- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
