# D1 Event Sourcing with Append-Only Event Log

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You need a reliable audit trail and the ability to replay or project application state from raw events, without a dedicated event-streaming platform. D1's append-only insertion pattern combined with SQLite's sequential rowid gives you a durable, ordered event log backed by Cloudflare's edge infrastructure.

## Context
Event sourcing stores state changes as a sequence of immutable events rather than mutating rows in place. D1's SQLite engine guarantees strict write ordering within a database, and its autoincrement `event_id` provides a monotonic sequence number suitable for event ordering within a single aggregate. For Cloudflare Workers applications that cannot afford the operational overhead of Kafka or EventBridge, D1 offers a practical event log with low-latency reads and transactional appends.

## Schema Design

```sql
-- migrations/0020_event_store.sql
CREATE TABLE IF NOT EXISTS events (
  event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  aggregate_type TEXT    NOT NULL,          -- e.g. 'Order', 'User'
  aggregate_id   TEXT    NOT NULL,          -- UUID or domain ID
  event_type     TEXT    NOT NULL,          -- e.g. 'OrderPlaced', 'ItemAdded'
  payload        TEXT    NOT NULL,          -- JSON blob
  metadata       TEXT    NOT NULL DEFAULT '{}', -- correlation_id, causation_id, actor
  occurred_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_events_aggregate ON events (aggregate_type, aggregate_id, event_id);
CREATE INDEX idx_events_type_ts   ON events (event_type, occurred_at);

-- Projection checkpoint: last event_id consumed by each projector
CREATE TABLE IF NOT EXISTS projector_checkpoints (
  projector_name TEXT    PRIMARY KEY,
  last_event_id  INTEGER NOT NULL DEFAULT 0,
  updated_at     INTEGER NOT NULL DEFAULT (unixepoch())
);
```

## Appending Events

```typescript
// src/event-store.ts
export interface DomainEvent<T = unknown> {
  aggregateType: string;
  aggregateId:   string;
  eventType:     string;
  payload:       T;
  metadata?:     Record<string, unknown>;
  schemaVersion?: number;
}

export async function appendEvents(
  db: D1Database,
  events: DomainEvent[],
): Promise<number[]> {
  if (events.length === 0) return [];

  const stmts = events.map((e) =>
    db.prepare(
      `INSERT INTO events
         (aggregate_type, aggregate_id, event_type, payload, metadata, schema_version)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      e.aggregateType,
      e.aggregateId,
      e.eventType,
      JSON.stringify(e.payload),
      JSON.stringify(e.metadata ?? {}),
      e.schemaVersion ?? 1,
    )
  );

  const results = await db.batch(stmts);
  // Return the auto-assigned event_ids for correlation
  return results.map((r) => r.meta.last_row_id as number);
}
```

## Loading and Replaying an Aggregate

```typescript
// src/order-aggregate.ts
export interface OrderState {
  id:       string;
  status:   'pending' | 'confirmed' | 'shipped' | 'cancelled';
  items:    Array<{ sku: string; qty: number; price: number }>;
  total:    number;
}

type OrderEvent =
  | { eventType: 'OrderPlaced';    payload: { customerId: string; items: OrderState['items'] } }
  | { eventType: 'OrderConfirmed'; payload: { confirmedAt: number } }
  | { eventType: 'OrderCancelled'; payload: { reason: string } };

function applyEvent(state: OrderState, event: OrderEvent): OrderState {
  switch (event.eventType) {
    case 'OrderPlaced':
      return {
        ...state,
        status: 'pending',
        items:  event.payload.items,
        total:  event.payload.items.reduce((s, i) => s + i.qty * i.price, 0),
      };
    case 'OrderConfirmed':
      return { ...state, status: 'confirmed' };
    case 'OrderCancelled':
      return { ...state, status: 'cancelled' };
    default:
      return state;
  }
}

export async function loadOrder(
  db: D1Database,
  orderId: string,
  afterEventId = 0,
): Promise<{ state: OrderState; lastEventId: number }> {
  const { results } = await db.prepare(
    `SELECT event_id, event_type, payload
     FROM   events
     WHERE  aggregate_type = 'Order'
       AND  aggregate_id   = ?
       AND  event_id       > ?
     ORDER  BY event_id ASC`
  ).bind(orderId, afterEventId).all<{
    event_id: number; event_type: string; payload: string;
  }>();

  let state: OrderState = { id: orderId, status: 'pending', items: [], total: 0 };
  let lastEventId = afterEventId;

  for (const row of results) {
    const event = { eventType: row.event_type, payload: JSON.parse(row.payload) } as OrderEvent;
    state = applyEvent(state, event);
    lastEventId = row.event_id;
  }

  return { state, lastEventId };
}
```

## Building Read-Model Projections

```typescript
// src/projectors/order-summary-projector.ts
export async function runOrderSummaryProjector(
  db: D1Database,
  batchSize = 100,
): Promise<void> {
  const checkpoint = await db.prepare(
    `SELECT last_event_id FROM projector_checkpoints WHERE projector_name = ?`
  ).bind('order_summary').first<{ last_event_id: number }>();

  const fromEventId = checkpoint?.last_event_id ?? 0;

  const { results } = await db.prepare(
    `SELECT event_id, aggregate_id, event_type, payload
     FROM   events
     WHERE  aggregate_type = 'Order'
       AND  event_id > ?
     ORDER  BY event_id ASC
     LIMIT  ?`
  ).bind(fromEventId, batchSize).all<{
    event_id: number; aggregate_id: string; event_type: string; payload: string;
  }>();

  if (results.length === 0) return;

  const upserts = results
    .filter((r) => r.event_type === 'OrderPlaced')
    .map((r) => {
      const p = JSON.parse(r.payload);
      return db.prepare(
        `INSERT INTO order_summary (order_id, customer_id, total, status)
         VALUES (?, ?, ?, 'pending')
         ON CONFLICT (order_id) DO NOTHING`
      ).bind(r.aggregate_id, p.customerId, p.items.reduce((s: number, i: { qty: number; price: number }) => s + i.qty * i.price, 0));
    });

  const lastId = results[results.length - 1].event_id;
  const checkpointUpsert = db.prepare(
    `INSERT INTO projector_checkpoints (projector_name, last_event_id, updated_at)
     VALUES (?, ?, unixepoch())
     ON CONFLICT (projector_name)
     DO UPDATE SET last_event_id = excluded.last_event_id,
                   updated_at    = excluded.updated_at`
  ).bind('order_summary', lastId);

  await db.batch([...upserts, checkpointUpsert]);
}
```

## Optimistic Concurrency on Appends

Prevent concurrent writes from creating conflicting events on the same aggregate by checking the expected last event before inserting.

```typescript
export async function appendWithVersionCheck(
  db: D1Database,
  event: DomainEvent,
  expectedVersion: number, // 0 means aggregate must not yet exist
): Promise<void> {
  const { results } = await db.prepare(
    `SELECT MAX(event_id) AS ver
     FROM   events
     WHERE  aggregate_type = ? AND aggregate_id = ?`
  ).bind(event.aggregateType, event.aggregateId).all<{ ver: number | null }>();

  const currentVersion = results[0]?.ver ?? 0;
  if (currentVersion !== expectedVersion) {
    throw new Error(
      `Concurrency conflict: expected version ${expectedVersion}, got ${currentVersion}`
    );
  }

  await appendEvents(db, [event]);
}
```

## Anti-patterns
- Mutating rows in the `events` table — the log must be append-only; treat it as write-once
- Storing binary blobs in `payload` — use JSON strings for portability and queryability via `json_extract()`
- Running the projector inside the same request that appends events — decouple via a Cron Trigger or Queue consumer to avoid head-of-line blocking
- Replaying all events every request without a snapshot — implement aggregate snapshots once event counts exceed a few hundred per aggregate

## Gotchas
- D1 does not support sequences; `AUTOINCREMENT` guarantees monotonically increasing IDs but not gap-free sequences
- `last_row_id` in `D1Result.meta` is per-statement inside a `batch()`; collect it immediately after each statement result
- SQLite's `unixepoch()` returns seconds, not milliseconds — store additional precision in the payload if sub-second ordering matters
- Projectors must be idempotent: a crashed projector re-processes events from its last checkpoint, so read-model upserts must use `ON CONFLICT DO UPDATE`

## Verification

```bash
# Append a test event
wrangler d1 execute MY_DB --local --command \
  "INSERT INTO events (aggregate_type, aggregate_id, event_type, payload)
   VALUES ('Order', 'ord-001', 'OrderPlaced', '{\"customerId\":\"usr-1\",\"items\":[]}')"

# Replay aggregate
wrangler d1 execute MY_DB --local --command \
  "SELECT event_id, event_type, payload FROM events
   WHERE aggregate_type='Order' AND aggregate_id='ord-001'
   ORDER BY event_id ASC;"

# Check projector checkpoint
wrangler d1 execute MY_DB --local --command \
  "SELECT * FROM projector_checkpoints;"
```

## Related
- [d1-audit-event-log.md](d1-audit-event-log.md)
- [d1-upsert-conflict-resolution-workers.md](d1-upsert-conflict-resolution-workers.md)
- [d1-materialized-view-simulation-cron.md](d1-materialized-view-simulation-cron.md)
- [d1-migrations-wrangler-ci-cd.md](d1-migrations-wrangler-ci-cd.md)

## Sources
- Event Sourcing pattern: https://martinfowler.com/eaaDev/EventSourcing.html
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite AUTOINCREMENT semantics: https://www.sqlite.org/autoinc.html
