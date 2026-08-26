# Inbox Pattern for Idempotent Message Consumption

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your Cloudflare Queue consumer receives an `order.paid` message and triggers a
downstream action — provisioning a resource, charging a card, sending an email.
Cloudflare Queues guarantees **at-least-once** delivery: if the consumer Worker
throws or times out before ACKing, the message is redelivered. Without a guard,
the same event fires the downstream action twice.

You need a record that says "I have already processed message `msg_abc`" that is
checked atomically with the processing itself.

---

## Context

The **Inbox pattern** is the consumer-side complement to the Transactional
Outbox. It maintains an `inbox` table in D1. Before processing a message, the
consumer attempts to insert the message ID. If the insert succeeds (no
duplicate), processing proceeds. If the insert conflicts (already seen), the
consumer skips processing and ACKs the message — making the handler naturally
idempotent.

Cloudflare Queues delivers messages to a Worker's `queue` handler. The consumer
has up to 25 seconds of wall-clock time per batch. D1 is an excellent inbox
store because:

- It supports `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` for atomic
  deduplication.
- It lives in the same Cloudflare account, so latency from Workers is in the
  single-digit millisecond range.
- It can atomically record the inbox row and the business effect in one
  `batch()` call.

---

## Schema Design

```sql
-- migrations/002_create_inbox.sql

CREATE TABLE IF NOT EXISTS inbox (
  message_id   TEXT    PRIMARY KEY,   -- queue message ID or idempotency key
  event_type   TEXT    NOT NULL,
  processed_at INTEGER NOT NULL,      -- Unix ms when first processed
  consumer     TEXT    NOT NULL       -- which consumer processed it (for multi-consumer setups)
);

-- Housekeeping index for time-based pruning
CREATE INDEX IF NOT EXISTS idx_inbox_processed
  ON inbox (processed_at);
```

Keep the `message_id` as the primary key. D1 enforces uniqueness at the
B-tree level, so `INSERT OR IGNORE` is O(log n) and safe under concurrent
Workers instances.

---

## Consumer Worker

```typescript
// src/consumers/order-events-consumer.ts
import { Env } from '../types';

interface OrderPaidPayload {
  orderId: string;
  paidAt: number;
}

interface QueueMessage {
  id: string;           // Cloudflare-assigned message ID
  body: {
    id: string;         // application-level event ID from the outbox
    type: string;
    aggregateId: string;
    payload: OrderPaidPayload;
  };
  ack: () => void;
  retry: () => void;
}

export default {
  async queue(
    batch: MessageBatch<QueueMessage['body']>,
    env: Env,
  ): Promise<void> {
    for (const message of batch.messages) {
      await handleMessage(message, env);
    }
  },
};

async function handleMessage(
  message: Message<QueueMessage['body']>,
  env: Env,
): Promise<void> {
  // Use the application-level event ID (from the outbox) as the inbox key.
  // The Cloudflare queue message ID changes on each retry; the event ID is stable.
  const eventId = message.body.id;

  // Attempt to claim the inbox slot atomically
  const inserted = await claimInbox(eventId, message.body.type, env);

  if (!inserted) {
    // Already processed — just ACK and move on
    message.ack();
    return;
  }

  try {
    await processEvent(message.body, env);
    message.ack();
  } catch (err) {
    // Roll back the inbox claim so the message can be retried
    await releaseInbox(eventId, env);
    message.retry();
  }
}

async function claimInbox(
  eventId: string,
  eventType: string,
  env: Env,
): Promise<boolean> {
  const result = await env.DB.prepare(
    `INSERT OR IGNORE INTO inbox (message_id, event_type, processed_at, consumer)
     VALUES (?, ?, ?, ?)`
  ).bind(eventId, eventType, Date.now(), 'order-events-consumer').run();

  // rows_written will be 1 if inserted, 0 if already existed
  return result.meta.rows_written === 1;
}

async function releaseInbox(eventId: string, env: Env): Promise<void> {
  // Only release if the business logic failed — do not release on success
  await env.DB.prepare(
    `DELETE FROM inbox WHERE message_id = ?`
  ).bind(eventId).run();
}

async function processEvent(
  body: QueueMessage['body'],
  env: Env,
): Promise<void> {
  if (body.type === 'order.paid') {
    const { orderId } = body.payload as OrderPaidPayload;
    await env.DB.prepare(
      `UPDATE orders SET fulfillment_status = 'QUEUED' WHERE id = ?`
    ).bind(orderId).run();

    // Call an external fulfillment service
    const res = await fetch(env.FULFILLMENT_API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orderId }),
    });
    if (!res.ok) throw new Error(`Fulfillment API ${res.status}`);
  }
}
```

---

## Atomic Claim-and-Process with D1 Batch

When the business effect is a D1 write, you can combine the inbox claim and
the business write in a single `batch()` call, making them atomic:

```typescript
async function processEventAtomic(
  eventId: string,
  eventType: string,
  orderId: string,
  env: Env,
): Promise<'processed' | 'duplicate'> {
  const results = await env.DB.batch([
    // Step 1: Try to claim the inbox slot
    env.DB.prepare(
      `INSERT OR IGNORE INTO inbox (message_id, event_type, processed_at, consumer)
       VALUES (?, ?, ?, ?)`
    ).bind(eventId, eventType, Date.now(), 'order-events-consumer'),

    // Step 2: Apply the business effect in the same transaction
    env.DB.prepare(
      `UPDATE orders SET fulfillment_status = 'QUEUED' WHERE id = ?`
    ).bind(orderId),
  ]);

  const claimed = results[0].meta.rows_written === 1;
  return claimed ? 'processed' : 'duplicate';
}
```

If `INSERT OR IGNORE` writes 0 rows (duplicate), the batch still succeeds —
the `UPDATE` runs but is a no-op because the state is already correct from the
first processing. This is safe for idempotent business effects.

---

## Choosing the Deduplication Key

| Key type | Stability | Notes |
|---|---|---|
| Cloudflare Queue message ID | Changes on retry | Do not use; a retried message gets a new ID |
| Application event ID (outbox `id`) | Stable across retries | Best choice |
| User-supplied idempotency key | Stable | Good for API-driven flows |
| Content hash of the payload | Stable | Use when event ID is unavailable |

Always prefer a key embedded in the **message body** rather than the
transport-layer ID, because transport IDs are an implementation detail of
the queue system and may be regenerated on broker restart or requeue.

---

## Inbox Pruning

Inbox rows need not be kept forever. A Cron Trigger or the queue relay can prune
old rows after a safe retention window (typically 2× the maximum message
retention period, which is 4 days for Cloudflare Queues as of mid-2026):

```typescript
async function pruneInbox(env: Env): Promise<void> {
  // Keep 10 days to be safe; Queues max retention is 4 days
  const cutoff = Date.now() - 10 * 24 * 60 * 60 * 1000;
  await env.DB.prepare(
    `DELETE FROM inbox WHERE processed_at < ?`
  ).bind(cutoff).run();
}
```

---

## Anti-patterns

**Using KV for inbox deduplication**
KV `put()` and `get()` are not atomic. Two concurrent Worker instances can both
read "not found" and both proceed to process. Use D1 with `INSERT OR IGNORE`.

**Skipping the inbox when the external call is "obviously idempotent"**
External APIs may accept repeated calls without error but still produce duplicate
side effects (double-sending emails, double-charging). Always track at the inbox
layer regardless of downstream idempotency claims.

**Releasing the inbox row on every error**
If `processEvent` throws after a partial side effect (e.g. the DB write
succeeded but the HTTP call failed), re-inserting and retrying will re-run the
DB write. Design `processEvent` to be safe to re-run, or make inbox release
conditional on what failed.

**Unbounded inbox table growth**
Without pruning, the inbox table balloons. At D1 limits (10 GB per database as
of mid-2026) this becomes a billing and query performance issue.

---

## Gotchas

- **`rows_written` vs `changes`**: D1's `meta.rows_written` reflects rows
  actually written; `INSERT OR IGNORE` on a conflict writes 0 rows, which is
  how you detect a duplicate. Checking `meta.changes` behaves similarly but
  is less stable across D1 driver versions — prefer `rows_written`.

- **Batch atomicity scope**: `DB.batch()` wraps all statements in one SQLite
  transaction, but if any statement throws a syntax error, the entire batch
  fails. Validate SQL at deploy time, not at runtime.

- **Clock drift in `processed_at`**: Multiple Workers instances across PoPs
  use `Date.now()` independently. The column is used only for pruning, so
  minor drift is harmless.

- **Cloudflare Queues retry delay**: When `message.retry()` is called, the
  message re-enters the queue with a backoff delay (configurable, default 30s).
  During that window another Worker instance could receive the same message if
  the batch had partial failures. The inbox claim prevents double processing.

---

## Verification

```bash
# 1. Publish a test event with a known ID
wrangler queues publish events \
  --message '{"id":"test-evt-001","type":"order.paid","aggregateId":"ord_001","payload":{"orderId":"ord_001","paidAt":1724284800000}}'

# 2. Observe consumer Worker logs
wrangler tail order-events-consumer

# 3. Check inbox row was created
wrangler d1 execute MY_DB --command \
  "SELECT message_id, processed_at FROM inbox WHERE message_id = 'test-evt-001'"

# 4. Republish the same event ID and confirm it is skipped (no duplicate effect)
wrangler queues publish events \
  --message '{"id":"test-evt-001","type":"order.paid","aggregateId":"ord_001","payload":{"orderId":"ord_001","paidAt":1724284800000}}'

# 5. Confirm fulfillment_status was NOT changed a second time
wrangler d1 execute MY_DB --command \
  "SELECT id, fulfillment_status FROM orders WHERE id = 'ord_001'"
```

---

## Related

- `outbox-pattern-d1-reliable-publishing.md` — producer-side pattern; produces
  the stable event IDs that the inbox uses as deduplication keys.
- `idempotency-key-pattern-workers-d1.md` — HTTP-level idempotency using a
  similar D1 INSERT OR IGNORE approach.
- `dead-letter-queue-pattern.md` — what happens to messages that exhaust retries
  without ever being successfully processed.
- `fan-out-queues-workers.md` — deploying multiple consumer Workers for the same
  queue; each consumer needs its own inbox (or a shared one keyed by consumer
  name).

---

## Sources

- Microservices.io — Idempotent Consumer pattern:
  https://microservices.io/patterns/communication-style/idempotent-consumer.html
- Cloudflare Queues at-least-once delivery documentation:
  https://developers.cloudflare.com/queues/reference/delivery-guarantees/
- D1 INSERT OR IGNORE / ON CONFLICT syntax:
  https://www.sqlite.org/lang_conflict.html
- Cloudflare D1 batch API:
  https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
