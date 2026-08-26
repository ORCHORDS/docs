# Event Sourcing with D1: Append-Only Log

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application mutates shared state and you need a full audit trail, the ability to replay history, and derived read models that can be rebuilt from first principles. A traditional mutable-row approach loses history and makes temporal queries expensive.

## Context

Event sourcing stores every state change as an immutable event appended to a log. The current state is derived by replaying events. With Cloudflare D1 (SQLite at the edge) you get:

- An `events` table as the source of truth (append-only).
- A `projections` table for fast reads without full replay.
- Workers that append events and query projections.

---

## Section 1 — Schema

```sql
-- migrations/0001_events.sql

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  stream_id   TEXT    NOT NULL,
  stream_type TEXT    NOT NULL,
  event_type  TEXT    NOT NULL,
  payload     TEXT    NOT NULL,
  metadata    TEXT    NOT NULL DEFAULT '{}',
  position    INTEGER NOT NULL,
  occurred_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_events_stream_position
  ON events (stream_id, position);

CREATE INDEX IF NOT EXISTS ix_events_stream_id_position
  ON events (stream_id, position);

CREATE TABLE IF NOT EXISTS projections (
  stream_id      TEXT PRIMARY KEY,
  stream_type    TEXT NOT NULL,
  state          TEXT NOT NULL,
  last_event_id  INTEGER NOT NULL,
  last_position  INTEGER NOT NULL,
  updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
```

## Section 2 — Appending Events with Optimistic Concurrency

```typescript
// event-store.ts
export interface DomainEvent<T = unknown> {
  streamId: string;
  streamType: string;
  eventType: string;
  payload: T;
  metadata?: Record<string, unknown>;
}

export interface AppendResult {
  eventId: number;
  position: number;
}

export async function appendEvent<T>(
  db: D1Database,
  event: DomainEvent<T>,
  expectedPosition: number | null,
): Promise<AppendResult> {
  const posRow = await db
    .prepare('SELECT COALESCE(MAX(position), 0) AS max_pos FROM events WHERE stream_id = ?')
    .bind(event.streamId)
    .first<{ max_pos: number }>();

  const currentMax = posRow?.max_pos ?? 0;

  if (expectedPosition !== null && currentMax !== expectedPosition) {
    throw new Error(
      `Concurrency conflict on stream ${event.streamId}: ` +
        `expected position ${expectedPosition}, got ${currentMax}`,
    );
  }

  const result = await db
    .prepare(
      `INSERT INTO events (stream_id, stream_type, event_type, payload, metadata, position)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      event.streamId,
      event.streamType,
      event.eventType,
      JSON.stringify(event.payload),
      JSON.stringify(event.metadata ?? {}),
      currentMax + 1,
    )
    .run();

  return { eventId: Number(result.meta.last_row_id), position: currentMax + 1 };
}

export async function loadStream<T>(
  db: D1Database,
  streamId: string,
  fromPosition = 1,
): Promise<Array<{ position: number; eventType: string; payload: T; occurredAt: string }>> {
  const { results } = await db
    .prepare(
      'SELECT position, event_type, payload, occurred_at FROM events '
      + 'WHERE stream_id = ? AND position >= ? ORDER BY position ASC',
    )
    .bind(streamId, fromPosition)
    .all<{ position: number; event_type: string; payload: string; occurred_at: string }>();

  return results.map((r) => ({
    position: r.position,
    eventType: r.event_type,
    payload: JSON.parse(r.payload) as T,
    occurredAt: r.occurred_at,
  }));
}
```

## Section 3 — Projection Rebuild and Snapshot

```typescript
// projection.ts
export interface OrderState {
  orderId: string;
  status: 'pending' | 'confirmed' | 'shipped' | 'cancelled';
  items: Array<{ sku: string; qty: number; price: number }>;
  totalCents: number;
}

type OrderEvent =
  | { type: 'OrderPlaced'; customerId: string; items: OrderState['items'] }
  | { type: 'ItemAdded'; sku: string; qty: number; price: number }
  | { type: 'OrderConfirmed' }
  | { type: 'OrderShipped'; trackingNumber: string }
  | { type: 'OrderCancelled'; reason: string };

export function evolve(state: OrderState, event: { eventType: string; payload: unknown }): OrderState {
  const e = { type: event.eventType, ...(event.payload as object) } as OrderEvent;
  switch (e.type) {
    case 'OrderPlaced': {
      const total = e.items.reduce((s, i) => s + i.qty * i.price, 0);
      return { ...state, status: 'pending', items: e.items, totalCents: total };
    }
    case 'ItemAdded': {
      const items = [...state.items, { sku: e.sku, qty: e.qty, price: e.price }];
      return { ...state, items, totalCents: state.totalCents + e.qty * e.price };
    }
    case 'OrderConfirmed':
      return { ...state, status: 'confirmed' };
    case 'OrderShipped':
      return { ...state, status: 'shipped' };
    case 'OrderCancelled':
      return { ...state, status: 'cancelled' };
    default:
      return state;
  }
}

export async function getOrderState(db: D1Database, orderId: string): Promise<OrderState> {
  const snap = await db
    .prepare('SELECT state FROM projections WHERE stream_id = ?')
    .bind(orderId)
    .first<{ state: string }>();

  if (snap) return JSON.parse(snap.state) as OrderState;

  const events = await loadStream(db, orderId);
  const initial: OrderState = { orderId, status: 'pending', items: [], totalCents: 0 };
  const state = events.reduce(evolve, initial);

  const lastEvent = await db
    .prepare('SELECT id, position FROM events WHERE stream_id = ? ORDER BY position DESC LIMIT 1')
    .bind(orderId)
    .first<{ id: number; position: number }>();

  if (lastEvent) {
    await db
      .prepare(
        `INSERT INTO projections (stream_id, stream_type, state, last_event_id, last_position)
         VALUES (?, 'Order', ?, ?, ?)
         ON CONFLICT(stream_id) DO UPDATE SET
           state = excluded.state,
           last_event_id = excluded.last_event_id,
           last_position = excluded.last_position,
           updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')`,
      )
      .bind(orderId, JSON.stringify(state), lastEvent.id, lastEvent.position)
      .run();
  }

  return state;
}
```

## Section 4 — Worker Entry Point

```typescript
// worker.ts
import { appendEvent, loadStream } from './event-store';
import { getOrderState } from './projection';

export interface Env { DB: D1Database; }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    const getMatch = url.pathname.match(/^\/orders\/([\w-]+)$/);
    if (getMatch && request.method === 'GET') {
      return Response.json(await getOrderState(env.DB, getMatch[1]));
    }

    const postMatch = url.pathname.match(/^\/orders\/([\w-]+)\/events$/);
    if (postMatch && request.method === 'POST') {
      const orderId = postMatch[1];
      const { eventType, payload, expectedPosition } = await request.json<{
        eventType: string;
        payload: unknown;
        expectedPosition: number | null;
      }>();
      const result = await appendEvent(
        env.DB,
        { streamId: orderId, streamType: 'Order', eventType, payload },
        expectedPosition,
      );
      return Response.json(result, { status: 201 });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Anti-patterns

- Mutating events: events are immutable; issue a corrective event instead of `UPDATE`.
- Not including a per-stream `position` column: concurrent appends cannot detect conflicts without it.
- Storing large blobs in event rows: keep events < 1 KB; reference R2 objects by key.
- Skipping snapshots on long streams: full replay will hit D1's 10 ms CPU query limit.

## Gotchas

- D1 is SQLite; use `AUTOINCREMENT` on `id` for a true monotonic global sequence.
- The `UNIQUE` constraint on `(stream_id, position)` provides optimistic concurrency; the application layer reads `MAX(position)` and the DB enforces uniqueness.
- `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` gives millisecond precision in SQLite.
- D1 auto-commits; there is no multi-statement transaction across append + snapshot update.

## Verification

```bash
curl -s -X POST https://worker.example.com/orders/order-123/events \
  -H 'Content-Type: application/json' \
  -d '{"eventType":"OrderPlaced","payload":{"customerId":"c1","items":[{"sku":"A","qty":2,"price":500}]},"expectedPosition":null}'

curl -s -X POST https://worker.example.com/orders/order-123/events \
  -H 'Content-Type: application/json' \
  -d '{"eventType":"OrderConfirmed","payload":{},"expectedPosition":1}'

curl -s https://worker.example.com/orders/order-123 | jq .

wrangler d1 execute <DB_NAME> --command \
  "SELECT id, event_type, position, occurred_at FROM events WHERE stream_id='order-123' ORDER BY position"
```

## Related

- documentation/categories/patterns/two-phase-commit-workers-d1-kv.md
- documentation/categories/patterns/idempotent-receiver-workers-kv.md

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/autoinc.html
- Greg Young, *Event Sourcing*, 2010
