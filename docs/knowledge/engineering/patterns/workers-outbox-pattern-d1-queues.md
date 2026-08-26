# Transactional Outbox Pattern with D1 + Queues

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Worker writes a record to D1 and then calls `queue.send()`. If the Worker crashes or the queue send fails after the D1 commit, the event is lost. Conversely, if the queue send succeeds but the D1 write fails (rolled back), a phantom event is emitted for a transaction that never committed.

You need an atomic guarantee: either both the business record and the outbound event are durably persisted, or neither is.

---

## Context

D1 supports multi-statement transactions. Cloudflare Queues do not participate in D1 transactions. The two systems cannot commit atomically. Classic two-phase commit is unavailable at the edge.

The Transactional Outbox pattern solves this by writing events into an `outbox` table inside the same D1 transaction as the business data. A separate relay Worker periodically polls the outbox and forwards undelivered rows into the queue, then marks them delivered. The relay is the only component that touches the queue; the business Worker never calls `queue.send()` directly.

---

## Solution

### Schema

```sql
-- migrations/0001_outbox.sql
CREATE TABLE IF NOT EXISTS outbox (
  id          TEXT PRIMARY KEY,          -- UUID v4, used as idempotency key
  topic       TEXT NOT NULL,
  payload     TEXT NOT NULL,             -- JSON
  created_at  TEXT NOT NULL,
  delivered_at TEXT,                     -- NULL = pending
  attempt_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending
  ON outbox (delivered_at, created_at)
  WHERE delivered_at IS NULL;
```

### Business Worker — atomic write

```typescript
// business-worker/src/index.ts
import { nanoid } from 'nanoid';

export interface Env {
  DB: D1Database;
}

interface OrderPayload {
  customerId: string;
  items: Array<{ sku: string; qty: number }>;
  totalCents: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body: OrderPayload = await request.json();
    const orderId = nanoid();
    const outboxId = nanoid(); // separate ID for the outbox row
    const now = new Date().toISOString();

    const event = {
      eventId: outboxId,
      eventType: 'order.created',
      orderId,
      customerId: body.customerId,
      totalCents: body.totalCents,
      occurredAt: now,
    };

    // Single D1 transaction — both writes commit or both roll back
    await env.DB.batch([
      env.DB.prepare(
        'INSERT INTO orders (id, customer_id, total_cents, created_at) VALUES (?, ?, ?, ?)'
      ).bind(orderId, body.customerId, body.totalCents, now),

      env.DB.prepare(
        'INSERT INTO outbox (id, topic, payload, created_at) VALUES (?, ?, ?, ?)'
      ).bind(outboxId, 'order.created', JSON.stringify(event), now),
    ]);

    return new Response(JSON.stringify({ orderId }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

### Relay Worker — polls and forwards

```typescript
// relay-worker/src/index.ts
export interface Env {
  DB: D1Database;
  QUEUE_EVENTS: Queue;
}

const BATCH_SIZE = 50;
const RELAY_INTERVAL_SECONDS = 5;

interface OutboxRow {
  id: string;
  topic: string;
  payload: string;
  attempt_count: number;
}

export default {
  // Triggered by a Cron Trigger every minute (minimum granularity);
  // loop internally for sub-minute cadence.
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runRelay(env));
  },
};

async function runRelay(env: Env): Promise<void> {
  // Run multiple passes within the scheduled invocation window
  for (let pass = 0; pass < 12; pass++) {
    const processed = await relayBatch(env);
    if (processed === 0) break; // Nothing pending — stop early
    await sleep(RELAY_INTERVAL_SECONDS * 1000);
  }
}

async function relayBatch(env: Env): Promise<number> {
  const { results } = await env.DB.prepare(
    `SELECT id, topic, payload, attempt_count
     FROM outbox
     WHERE delivered_at IS NULL
     ORDER BY created_at ASC
     LIMIT ?`
  ).bind(BATCH_SIZE).all<OutboxRow>();

  if (!results || results.length === 0) return 0;

  const sends: Array<MessageSendRequest<unknown>> = results.map((row) => ({
    body: JSON.parse(row.payload),
    contentType: 'json',
  }));

  // sendBatch is atomic at the queue level — all or nothing
  await env.QUEUE_EVENTS.sendBatch(sends);

  // Mark delivered inside D1
  const deliveredAt = new Date().toISOString();
  const ids = results.map((r) => r.id);
  const placeholders = ids.map(() => '?').join(', ');

  await env.DB.prepare(
    `UPDATE outbox
     SET delivered_at = ?, attempt_count = attempt_count + 1
     WHERE id IN (${placeholders})`
  ).bind(deliveredAt, ...ids).run();

  return results.length;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
```

### Consumer — idempotent processing

```typescript
// consumer-worker/src/index.ts
export interface Env {
  DB: D1Database;
}

interface OrderCreatedEvent {
  eventId: string;
  eventType: string;
  orderId: string;
  customerId: string;
  totalCents: number;
  occurredAt: string;
}

export default {
  async queue(batch: MessageBatch<OrderCreatedEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body;

      try {
        // Idempotency check — skip if already processed
        const existing = await env.DB.prepare(
          'SELECT 1 FROM processed_events WHERE event_id = ?'
        ).bind(event.eventId).first();

        if (existing) {
          msg.ack(); // Already handled — safe to ack
          continue;
        }

        await processOrderCreated(event, env);

        await env.DB.prepare(
          'INSERT INTO processed_events (event_id, processed_at) VALUES (?, ?)'
        ).bind(event.eventId, new Date().toISOString()).run();

        msg.ack();
      } catch (err) {
        console.error(JSON.stringify({ type: 'consumer_error', eventId: event.eventId, error: String(err) }));
        msg.retry();
      }
    }
  },
};

async function processOrderCreated(event: OrderCreatedEvent, env: Env): Promise<void> {
  // Downstream business logic: send email, update inventory, etc.
  await env.DB.prepare(
    'INSERT INTO fulfillment_queue (order_id, status, created_at) VALUES (?, ?, ?)'
  ).bind(event.orderId, 'pending', event.occurredAt).run();
}
```

### Cleanup job — remove delivered rows

```typescript
// cleanup-worker/src/index.ts
export interface Env {
  DB: D1Database;
}

const RETENTION_DAYS = 7;

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = new Date(Date.now() - RETENTION_DAYS * 86_400_000).toISOString();
    const result = await env.DB.prepare(
      'DELETE FROM outbox WHERE delivered_at IS NOT NULL AND delivered_at < ?'
    ).bind(cutoff).run();

    console.log(JSON.stringify({
      type: 'outbox_cleanup',
      deleted: result.meta.changes,
      cutoff,
    }));
  },
};
```

---

## Implementation Details

**D1 batch vs. transaction:** `env.DB.batch([...])` executes all statements in a single implicit transaction. If any statement fails, all are rolled back. Prefer batch for multi-statement atomicity.

**Relay cadence:** Cloudflare Cron Triggers have a 1-minute minimum. For lower latency, run multiple passes with `sleep()` inside a single invocation as shown above.

**Message ordering:** `sendBatch` does not guarantee ordering within the batch. If downstream consumers require ordered processing, include a sequence number or `occurredAt` timestamp in the event and sort on the consumer side.

**Outbox row size:** D1 rows are limited to 1 MB. Keep event payloads lean; store large blobs in R2 and include only the R2 key in the outbox payload.

**At-least-once guarantee:** The relay may deliver a message and then fail before marking the row delivered. On the next pass it delivers again. Consumers must be idempotent — the `processed_events` deduplication table handles this.

---

## Anti-patterns

- **Writing to the queue inside the D1 transaction:** Not possible — D1 transactions are SQL-only. Attempting to mix queue sends with SQL in a transaction leaves you with the original dual-write problem.
- **Polling the outbox from the business Worker on every request:** This couples read latency to outbox depth. Use a dedicated relay Worker.
- **Deleting outbox rows immediately after send:** Retain rows for audit and replay. Mark delivered; delete on a schedule.
- **No idempotency key in the event:** Without a stable `eventId`, consumers cannot detect duplicates safely.

---

## Gotchas

- D1 in Workers is region-pinned per request for consistency. The relay Worker may hit a different D1 region on a cold start. This is fine — the index on `(delivered_at, created_at)` keeps queries efficient regardless of region.
- `sendBatch` accepts a maximum of 100 messages per call. For larger batches, chunk the array and call `sendBatch` in a loop.
- The `processed_events` table grows indefinitely. Add a similar cleanup job scoped to rows older than your idempotency window (typically 24–72 hours).
- Wrangler Cron Triggers require at least one route or a `[triggers]` block in `wrangler.toml`.

---

## Verification

1. Write 100 orders while the relay Worker is paused (disable the cron). Confirm all 100 outbox rows exist with `delivered_at IS NULL`.
2. Enable the relay. Confirm all 100 rows transition to `delivered_at IS NOT NULL` within 2 minutes.
3. Simulate a relay crash mid-batch by injecting a deliberate error. Confirm re-run delivers remaining rows without duplicating already-delivered events in the consumer.
4. Submit the same event payload twice with the same `eventId`. Confirm the consumer's `processed_events` deduplication skips the second delivery.

---

## Related

- `workers-bulkhead-pattern-queue-isolation.md` — routing events into isolated queues after outbox relay
- `workers-compensating-transaction-pattern.md` — rolling back multi-step sagas
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch

---

## Sources

- Microservices Patterns — Chris Richardson, Chapter 3: Managing transactions with sagas (Outbox pattern)
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare Queues sendBatch: https://developers.cloudflare.com/queues/configuration/javascript-apis/#producer
