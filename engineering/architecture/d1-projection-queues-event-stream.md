# D1 Projection from a Queues Event Stream

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

The example project platform appends domain events to an append-only D1 event store (or emits them onto a
Cloudflare Queue). Downstream features — order summaries, tenant dashboards, search indexes — need
query-friendly read models that are not practical to derive with complex SQL over the raw event log
at request time. You want to project events asynchronously into denormalised D1 tables that a
Worker can query with simple SELECT statements, without coupling the write side to the read side or
running projections inside the user-facing request.

## Context

In Event Sourcing / CQRS, a **projection** is a consumer that reads the ordered stream of domain
events and applies them one-by-one to build or update a read model. On Cloudflare: the event stream
is a Queue, the projection logic runs in a Queue consumer Worker, and the read model lives in a D1
database. This article covers: event envelope design, Queue consumer projection loop, idempotency
via checkpoint tracking, catch-up rebuild, and projection versioning.

---

## Event Envelope Schema

```typescript
// packages/shared-kernel/src/domain-event.ts

export interface DomainEvent<T = unknown> {
  eventId:       string;          // globally unique, used for idempotency
  eventType:     string;          // "OrderPlaced" | "PaymentFailed" | ...
  aggregateId:   string;          // entity this event belongs to
  aggregateType: string;          // "Order" | "Payment" | ...
  occurredAt:    number;          // ms epoch
  sequenceNumber: number;         // monotonic per-aggregate sequence
  payload:       T;
  metadata: {
    tenantId:      string;
    correlationId: string;
    causationId:   string;        // eventId of the event that caused this one
  };
}
```

---

## D1 Read Model Tables

```sql
-- migrations/0010_order_summary_projection.sql

-- Checkpoint table: tracks the last processed eventId per projection
CREATE TABLE IF NOT EXISTS projection_checkpoint (
  projection_name TEXT PRIMARY KEY,
  last_event_id   TEXT NOT NULL DEFAULT '',
  last_sequence   INTEGER NOT NULL DEFAULT 0,
  updated_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Denormalised read model: one row per order
CREATE TABLE IF NOT EXISTS order_summary (
  order_id        TEXT PRIMARY KEY,
  tenant_id       TEXT NOT NULL,
  customer_name   TEXT,
  total_cents     INTEGER NOT NULL DEFAULT 0,
  currency        TEXT NOT NULL DEFAULT 'USD',
  status          TEXT NOT NULL DEFAULT 'pending',
  item_count      INTEGER NOT NULL DEFAULT 0,
  placed_at       INTEGER,
  paid_at         INTEGER,
  cancelled_at    INTEGER,
  last_event_id   TEXT NOT NULL DEFAULT '',
  updated_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_order_summary_tenant
  ON order_summary (tenant_id, placed_at DESC);

CREATE INDEX IF NOT EXISTS idx_order_summary_status
  ON order_summary (tenant_id, status, placed_at DESC);
```

---

## Queue Consumer — Projection Worker

```typescript
// workers/order-projection/src/index.ts
import type { D1Database, Queue } from '@cloudflare/workers-types';
import type { DomainEvent } from '@example project/shared-kernel/domain-event';

interface Env {
  DB: D1Database;
}

const PROJECTION_NAME = 'order_summary_v1';

type OrderEvent =
  | DomainEvent<{ customerId: string; customerName: string; currency: string }>
  | DomainEvent<{ itemId: string; qty: number; unitCents: number }>
  | DomainEvent<{ totalCents: number; paidAt: number }>
  | DomainEvent<{ reason: string; cancelledAt: number }>;

export default {
  async queue(
    batch: MessageBatch<DomainEvent>,
    env: Env,
  ): Promise<void> {
    // Sort by occurredAt + sequenceNumber to handle out-of-order delivery
    const events = [...batch.messages]
      .map((m) => m.body)
      .sort((a, b) =>
        a.occurredAt !== b.occurredAt
          ? a.occurredAt - b.occurredAt
          : a.sequenceNumber - b.sequenceNumber,
      );

    for (const event of events) {
      try {
        await applyEvent(env.DB, event);
      } catch (err) {
        // Log and continue — do not let one bad event block the whole batch.
        // Send to DLQ via Queue retry settings.
        console.error({ eventId: event.eventId, error: String(err) });
      }
    }

    // Acknowledge all messages; individual failures are tracked via DLQ
    batch.ackAll();
  },
};

async function applyEvent(db: D1Database, event: DomainEvent): Promise<void> {
  // Idempotency check: skip if we've already processed this eventId
  const checkpoint = await db
    .prepare(
      `SELECT last_event_id FROM projection_checkpoint
       WHERE projection_name = ?`,
    )
    .bind(PROJECTION_NAME)
    .first<{ last_event_id: string }>();

  // Note: checkpoint only guards against re-processing old batches after a rebuild.
  // Per-event idempotency uses the `last_event_id` column on the target row.
  const existing = await db
    .prepare('SELECT last_event_id FROM order_summary WHERE order_id = ?')
    .bind(event.aggregateId)
    .first<{ last_event_id: string }>();

  if (existing?.last_event_id === event.eventId) {
    return; // Already applied — idempotent skip
  }

  const handler = HANDLERS[event.eventType];
  if (!handler) return; // Unknown event type — ignore

  await handler(db, event);

  // Advance checkpoint
  await db
    .prepare(
      `INSERT INTO projection_checkpoint (projection_name, last_event_id, last_sequence, updated_at)
       VALUES (?, ?, ?, unixepoch())
       ON CONFLICT (projection_name) DO UPDATE
         SET last_event_id = excluded.last_event_id,
             last_sequence  = excluded.last_sequence,
             updated_at     = excluded.updated_at`,
    )
    .bind(PROJECTION_NAME, event.eventId, event.sequenceNumber)
    .run();
}
```

---

## Event Handler Implementations

```typescript
// workers/order-projection/src/handlers.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { DomainEvent } from '@example project/shared-kernel/domain-event';

export const HANDLERS: Record<
  string,
  (db: D1Database, event: DomainEvent<any>) => Promise<void>
> = {
  async OrderPlaced(db, event) {
    const { customerName, currency } = event.payload;
    await db
      .prepare(
        `INSERT INTO order_summary
           (order_id, tenant_id, customer_name, currency, status, placed_at, last_event_id, updated_at)
         VALUES (?, ?, ?, ?, 'pending', ?, ?, unixepoch())
         ON CONFLICT (order_id) DO UPDATE
           SET customer_name  = excluded.customer_name,
               placed_at      = excluded.placed_at,
               status         = 'pending',
               last_event_id  = excluded.last_event_id,
               updated_at     = excluded.updated_at`,
      )
      .bind(
        event.aggregateId,
        event.metadata.tenantId,
        customerName,
        currency,
        Math.floor(event.occurredAt / 1000),
        event.eventId,
      )
      .run();
  },

  async OrderItemAdded(db, event) {
    const { qty, unitCents } = event.payload;
    const lineCents = qty * unitCents;
    await db
      .prepare(
        `UPDATE order_summary
         SET total_cents    = total_cents + ?,
             item_count     = item_count + ?,
             last_event_id  = ?,
             updated_at     = unixepoch()
         WHERE order_id = ?`,
      )
      .bind(lineCents, qty, event.eventId, event.aggregateId)
      .run();
  },

  async PaymentConfirmed(db, event) {
    const { paidAt } = event.payload;
    await db
      .prepare(
        `UPDATE order_summary
         SET status        = 'paid',
             paid_at       = ?,
             last_event_id = ?,
             updated_at    = unixepoch()
         WHERE order_id = ?`,
      )
      .bind(Math.floor(paidAt / 1000), event.eventId, event.aggregateId)
      .run();
  },

  async OrderCancelled(db, event) {
    const { cancelledAt } = event.payload;
    await db
      .prepare(
        `UPDATE order_summary
         SET status        = 'cancelled',
             cancelled_at  = ?,
             last_event_id = ?,
             updated_at    = unixepoch()
         WHERE order_id = ?`,
      )
      .bind(Math.floor(cancelledAt / 1000), event.eventId, event.aggregateId)
      .run();
  },
};
```

---

## Catch-Up Rebuild from Event Store

When you release a new projection version (e.g. `order_summary_v2`), you need to replay all
historical events. The rebuild Worker reads from D1 event store in batches and re-enqueues:

```typescript
// workers/projection-rebuild/src/index.ts
interface Env {
  DB:              D1Database;
  ORDER_QUEUE:     Queue<DomainEvent>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const body = await request.json<{ fromSequence?: number; aggregateType?: string }>();
    const from = body.fromSequence ?? 0;

    // Read events in pages of 500 and re-emit to Queue
    let cursor = from;
    let total  = 0;

    while (true) {
      const batch = await env.DB
        .prepare(
          `SELECT * FROM domain_events
           WHERE sequence_number > ?
             AND (? IS NULL OR aggregate_type = ?)
           ORDER BY sequence_number ASC
           LIMIT 500`,
        )
        .bind(cursor, body.aggregateType ?? null, body.aggregateType ?? null)
        .all<DomainEvent>();

      if (batch.results.length === 0) break;

      await env.ORDER_QUEUE.sendBatch(
        batch.results.map((e) => ({ body: e, contentType: 'json' })),
      );

      cursor = batch.results[batch.results.length - 1].sequenceNumber;
      total += batch.results.length;
    }

    return Response.json({ replayed: total });
  },
};
```

The Queue consumer's idempotency guard (`last_event_id` check) ensures duplicate delivery during
rebuild does not corrupt the read model.

---

## Projection Versioning Strategy

```sql
-- Drop and recreate read model for a v2 projection during off-peak hours
-- Run via a scheduled Worker or manual trigger

-- Step 1: create the new table
CREATE TABLE IF NOT EXISTS order_summary_v2 (
  order_id      TEXT PRIMARY KEY,
  -- new fields ...
);

-- Step 2: rebuild from event store (see rebuild Worker above)

-- Step 3: swap references via a view
DROP VIEW IF EXISTS order_summary_current;
CREATE VIEW order_summary_current AS SELECT * FROM order_summary_v2;

-- Step 4: drop old table after traffic is confirmed on v2
DROP TABLE IF EXISTS order_summary;
```

During the rebuild, the v1 table continues serving reads. The view swap is atomic within SQLite.

---

## Anti-patterns

- **Querying the event store on the request path**: The read model exists precisely to avoid this.
  If `order_summary` does not have a field you need, add it to the projection — do not JOIN back to
  the event store at query time.
- **Using `occurredAt` as the only sort key**: Queue delivery is not guaranteed in order. Always
  sort by `(occurredAt, sequenceNumber)` inside the consumer before applying events.
- **Sharing a D1 database between write model and read model**: Schema migrations on the write side
  can block read model queries. Give each a separate D1 database or at minimum separate the tables
  with a naming convention and separate migration files.
- **Rebuilding via a single long-running Worker request**: Workers have a 30-second CPU limit on the
  paid plan. Batch the rebuild into Queue messages so the work is resumable.
- **Dropping the projection checkpoint**: Without a checkpoint, a re-deployed projection consumer
  cannot distinguish "new events" from "already processed events" after a cold start.

---

## Gotchas

- D1 `batch()` is limited to 100 statements. When a Queue batch contains more than 100 events, use
  a loop with individual `run()` calls grouped by transaction manually, or split into multiple
  `batch()` calls.
- `batch.ackAll()` in the Queue consumer means the whole batch is acknowledged even if some events
  failed. This is intentional for projection resilience — failed events should go to a DLQ
  configured in `wrangler.jsonc`, not block the whole batch.
- Analytics Engine is write-only from Workers; you cannot query it in the consumer. Keep the
  checkpoint state in D1, not Analytics Engine.
- Cloudflare Queues has a maximum message size of 128 KB. Large event payloads (e.g. file metadata)
  must use the claim-check pattern: store the payload in R2 and put only the R2 key in the Queue
  message.
- When rebuilding, the consumer may process a mix of historical and live events concurrently.
  Ensure the `(occurredAt, sequenceNumber)` sort order is preserved across the queue and the event
  store pages.

---

## Verification

```bash
# 1. Publish a test OrderPlaced event via the Queue
wrangler queues send order-events '{
  "eventId":"evt_001","eventType":"OrderPlaced",
  "aggregateId":"ord_001","aggregateType":"Order",
  "occurredAt":1724400000000,"sequenceNumber":1,
  "payload":{"customerName":"Alice","currency":"USD"},
  "metadata":{"tenantId":"ten_abc","correlationId":"corr_001","causationId":""}
}'

# 2. Wait ~1 second for the consumer to process
# 3. Query the read model
wrangler d1 execute example project-db --local \
  --command "SELECT * FROM order_summary WHERE order_id = 'ord_001'"

# Expected: row with status='pending', customer_name='Alice'
```

---

## Related

- `/documentation/categories/architecture/event-sourcing-d1-append-only-store.md`
- `/documentation/categories/architecture/cqrs-cloudflare-workers-d1.md`
- `/documentation/categories/architecture/read-model-projection-workers-kv-cqrs.md`
- `/documentation/categories/architecture/outbox-pattern-workers-queues-reliable-events.md`
- `/documentation/categories/architecture/dead-letter-queue-architecture.md`
- `/documentation/categories/architecture/poison-pill-message-handling-workers-queues.md`

---

## Sources

- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Greg Young — "CQRS and Event Sourcing" (GOTO 2014, YouTube)
- Vaughn Vernon — "Implementing Domain-Driven Design" (projection patterns)
- Martin Fowler — "Event Sourcing" pattern: https://martinfowler.com/eaaDev/EventSourcing.html
