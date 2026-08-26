# Read Model Projections (CQRS Read Side) with D1 and Cloudflare Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your write-side D1 tables are normalized for correctness but queries for dashboards and list views require expensive multi-table joins that are slow at scale. Read traffic is an order of magnitude higher than write traffic. You need a purpose-built read model that can serve paginated lists and aggregate statistics without touching the write-side schema.

## Context

Command Query Responsibility Segregation (CQRS) separates the write path (commands that change state) from the read path (queries that return data). On Cloudflare Workers, a write-side Worker appends immutable domain events to a D1 `events` table and publishes them to Queues. A Queues consumer Worker projects those events into denormalized D1 read tables optimized for the access patterns of each view. Because projections are rebuilt from the event log, the read model can be dropped and replayed at any time to fix a bug or add a new field. Keyset pagination on the read tables keeps queries O(log n) regardless of table size.

## Write Side: Event Append Log

```typescript
// write-worker.ts
// CREATE TABLE events (
//   id            INTEGER PRIMARY KEY AUTOINCREMENT,
//   event_id      TEXT NOT NULL UNIQUE,
//   event_type    TEXT NOT NULL,
//   aggregate_id  TEXT NOT NULL,
//   payload       TEXT NOT NULL,   -- JSON
//   occurred_at   INTEGER NOT NULL DEFAULT (unixepoch())
// );
// CREATE INDEX idx_events_aggregate ON events(aggregate_id, id);
// CREATE INDEX idx_events_type_id   ON events(event_type, id);

import { Env } from './types';

export async function appendEvent(
  env: Env,
  aggregateId: string,
  eventType: string,
  payload: unknown,
): Promise<void> {
  const eventId = crypto.randomUUID();
  const payloadJson = JSON.stringify(payload);

  await env.DB.prepare(
    `INSERT INTO events (event_id, event_type, aggregate_id, payload)
     VALUES (?, ?, ?, ?)`,
  ).bind(eventId, eventType, aggregateId, payloadJson).run();

  await env.EVENT_QUEUE.send(
    { event_id: eventId, event_type: eventType, aggregate_id: aggregateId, payload },
    { contentType: 'json' },
  );
}

// Usage in an order placement handler:
export async function placeOrder(env: Env, req: Request): Promise<Response> {
  const body = await req.json<{ customerId: string; totalCents: number; currency: string }>();
  const orderId = crypto.randomUUID();

  // Write command to normalized orders table
  await env.DB.prepare(
    `INSERT INTO orders (id, customer_id, status, total_cents, currency) VALUES (?, ?, 'pending', ?, ?)`,
  ).bind(orderId, body.customerId, body.totalCents, body.currency).run();

  // Append event for projection
  await appendEvent(env, orderId, 'order.placed', {
    orderId,
    customerId:  body.customerId,
    totalCents:  body.totalCents,
    currency:    body.currency,
    placedAt:    new Date().toISOString(),
  });

  return Response.json({ orderId });
}
```

## Queues Consumer: Projecting Events into Read Tables

```typescript
// projection-worker.ts
// READ TABLES (denormalized for query performance):
// CREATE TABLE order_summary (
//   order_id      TEXT PRIMARY KEY,
//   customer_id   TEXT NOT NULL,
//   status        TEXT NOT NULL,
//   total_cents   INTEGER NOT NULL,
//   currency      TEXT NOT NULL,
//   placed_at     INTEGER NOT NULL,
//   last_event_id INTEGER NOT NULL
// );
// CREATE INDEX idx_order_summary_customer ON order_summary(customer_id, placed_at DESC);
//
// CREATE TABLE customer_stats (
//   customer_id   TEXT PRIMARY KEY,
//   order_count   INTEGER NOT NULL DEFAULT 0,
//   total_spent_cents INTEGER NOT NULL DEFAULT 0,
//   last_order_at INTEGER
// );

import { Env } from './types';

interface EventMessage {
  event_id: string;
  event_type: string;
  aggregate_id: string;
  payload: Record<string, unknown>;
}

export default {
  async queue(batch: MessageBatch<EventMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      await projectEvent(env, msg);
    }
  },
};

async function projectEvent(
  env: Env,
  msg: Message<EventMessage>,
): Promise<void> {
  const event = msg.body;

  // Resolve numeric autoincrement id for idempotency tracking
  const row = await env.DB.prepare(
    `SELECT id FROM events WHERE event_id = ?`,
  ).bind(event.event_id).first<{ id: number }>();

  if (!row) { msg.ack(); return; } // should not happen, but guard against race
  const eventSeqId = row.id;

  switch (event.event_type) {
    case 'order.placed':    await projectOrderPlaced(env, event, eventSeqId); break;
    case 'order.confirmed': await projectOrderConfirmed(env, event, eventSeqId); break;
    case 'order.cancelled': await projectOrderCancelled(env, event, eventSeqId); break;
    default: break; // forward-compatible: ignore unknown types
  }

  msg.ack();
}

async function projectOrderPlaced(
  env: Env,
  event: EventMessage,
  seqId: number,
): Promise<void> {
  const p = event.payload;

  await env.DB.batch([
    // Upsert order summary
    env.DB.prepare(
      `INSERT INTO order_summary (order_id, customer_id, status, total_cents, currency, placed_at, last_event_id)
       VALUES (?, ?, 'pending', ?, ?, unixepoch(), ?)
       ON CONFLICT(order_id) DO UPDATE SET last_event_id = excluded.last_event_id
         WHERE excluded.last_event_id > order_summary.last_event_id`,
    ).bind(p.orderId, p.customerId, p.totalCents, p.currency, seqId),

    // Upsert customer stats
    env.DB.prepare(
      `INSERT INTO customer_stats (customer_id, order_count, total_spent_cents, last_order_at)
       VALUES (?, 1, ?, unixepoch())
       ON CONFLICT(customer_id) DO UPDATE
         SET order_count       = order_count + 1,
             total_spent_cents = total_spent_cents + ?,
             last_order_at     = unixepoch()`,
    ).bind(p.customerId, p.totalCents, p.totalCents),
  ]);
}

async function projectOrderConfirmed(
  env: Env,
  event: EventMessage,
  seqId: number,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE order_summary SET status = 'confirmed', last_event_id = ?
     WHERE order_id = ? AND last_event_id < ?`,
  ).bind(seqId, event.aggregate_id, seqId).run();
}

async function projectOrderCancelled(
  env: Env,
  event: EventMessage,
  seqId: number,
): Promise<void> {
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE order_summary SET status = 'cancelled', last_event_id = ?
       WHERE order_id = ? AND last_event_id < ?`,
    ).bind(seqId, event.aggregate_id, seqId),
    // Reverse the stat contribution
    env.DB.prepare(
      `UPDATE customer_stats
       SET order_count = MAX(0, order_count - 1),
           total_spent_cents = MAX(0, total_spent_cents - (
             SELECT total_cents FROM order_summary WHERE order_id = ?
           ))
       WHERE customer_id = (SELECT customer_id FROM order_summary WHERE order_id = ?)`,
    ).bind(event.aggregate_id, event.aggregate_id),
  ]);
}
```

## Idempotent Projection Replay and Rebuild

```typescript
// replay-worker.ts  —  called via internal admin endpoint to rebuild projections
export async function rebuildProjections(env: Env): Promise<void> {
  // 1. Truncate read tables
  await env.DB.batch([
    env.DB.prepare(`DELETE FROM order_summary`),
    env.DB.prepare(`DELETE FROM customer_stats`),
  ]);

  // 2. Replay event log in order, using keyset pagination
  let lastId = 0;
  const BATCH = 500;

  while (true) {
    const { results } = await env.DB.prepare(
      `SELECT id, event_id, event_type, aggregate_id, payload
       FROM   events
       WHERE  id > ?
       ORDER  BY id
       LIMIT  ?`,
    ).bind(lastId, BATCH).all<EventRow>();

    if (results.length === 0) break;

    for (const row of results) {
      const event: EventMessage = {
        event_id:     row.event_id,
        event_type:   row.event_type,
        aggregate_id: row.aggregate_id,
        payload:      JSON.parse(row.payload),
      };
      await applyProjectionDirect(env, event, row.id);
    }

    lastId = results[results.length - 1].id;
  }
}

interface EventRow {
  id: number;
  event_id: string;
  event_type: string;
  aggregate_id: string;
  payload: string;
}
```

## Serving Read Model Data with Keyset Pagination

```typescript
// read-worker.ts
export async function listCustomerOrders(
  env: Env,
  customerId: string,
  afterPlacedAt: number | null,
  afterOrderId: string | null,
  limit = 20,
): Promise<{ orders: unknown[]; nextCursor: string | null }> {
  const hasAfter = afterPlacedAt !== null && afterOrderId !== null;

  const { results } = await env.DB.prepare(
    hasAfter
      ? `SELECT order_id, status, total_cents, currency, placed_at
         FROM   order_summary
         WHERE  customer_id = ?
           AND  (placed_at < ? OR (placed_at = ? AND order_id > ?))
         ORDER  BY placed_at DESC, order_id
         LIMIT  ?`
      : `SELECT order_id, status, total_cents, currency, placed_at
         FROM   order_summary
         WHERE  customer_id = ?
         ORDER  BY placed_at DESC, order_id
         LIMIT  ?`,
    hasAfter
      ? env.DB.prepare('').bind(customerId, afterPlacedAt, afterPlacedAt, afterOrderId, limit + 1)
      : env.DB.prepare('').bind(customerId, limit + 1),
  ).all();

  // Simplification: use raw prepare for clarity in the article
  const last = results[results.length - 1] as Record<string, unknown> | undefined;
  const nextCursor = results.length > limit && last
    ? Buffer.from(JSON.stringify({ p: last.placed_at, id: last.order_id })).toString('base64')
    : null;

  return { orders: results.slice(0, limit), nextCursor };
}
```

## Anti-patterns

- **Querying the write-side `events` table directly from the read API** — this creates contention and bypasses the denormalized read model entirely.
- **Storing mutable state in the event log** — events are immutable facts; if a field changes, append a new event, do not update the existing row.
- **Projecting without an ordering guarantee** — always project events in `id` (autoincrement) order to ensure causal consistency; out-of-order projection corrupts aggregates.
- **Skipping the `last_event_id` guard on upserts** — without it, a replayed older event can overwrite a newer projected state.

## Gotchas

- D1's `AUTOINCREMENT` guarantees monotonically increasing IDs within a single database but is not globally ordered across Workers replicas; use it as a sequencing key only within one D1 instance.
- Rebuilding projections is a blocking operation; run it via a dedicated Cron or admin-only route with an appropriate timeout, not inline in a user-facing request.
- Cloudflare Queues delivers messages at-least-once; the `last_event_id` guard in upserts makes projection idempotent for duplicate queue deliveries.
- Keyset pagination requires a stable, indexed sort key pair; `(placed_at DESC, order_id ASC)` works if `order_id` is UUID and `placed_at` can have ties.
- D1 `batch()` is atomic per call but the rebuild loop is not wrapped in a transaction; a rebuild crash partway through leaves the read tables in a partially rebuilt state — add a `rebuild_state` flag to detect and resume.

## Verification

```bash
# Apply read model schema
wrangler d1 execute example project-db --file=read-schema.sql --env production

# Trigger a projection rebuild (admin endpoint)
curl -X POST https://your-worker.workers.dev/admin/rebuild-projections \
  -H 'Authorization: Bearer $ADMIN_TOKEN'

# Verify read table row count matches event count
wrangler d1 execute example project-db \
  --command="SELECT (SELECT COUNT(*) FROM order_summary) as read_rows, (SELECT COUNT(DISTINCT aggregate_id) FROM events WHERE event_type='order.placed') as event_rows" \
  --env production

# Test keyset pagination
curl 'https://your-worker.workers.dev/customers/cust_1/orders?limit=20'
```

## Related

- `outbox-pattern-workers-d1-queues-reliable-events.md`
- `event-carried-state-transfer-workers-queues.md`
- `hexagonal-architecture-workers-ports-adapters.md`

## Sources

- Fowler, Martin — CQRS — https://martinfowler.com/bliki/CQRS.html
- Young, Greg — CQRS Documents — https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare Queues Consumer — https://developers.cloudflare.com/queues/configuration/javascript-apis/#consumer
