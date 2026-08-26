# Append-Only Event Store in D1 with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a lightweight event-sourcing store that keeps the full audit history of domain object changes, supports replaying events to rebuild aggregate state at any point in time, and runs entirely within the Cloudflare stack without an external database. Mutable-record updates lose history and make debugging production issues nearly impossible.

---

## Context

D1 is SQLite at the edge, and SQLite's simplicity makes it an excellent append-only log: rows are never updated or deleted, only inserted, so the file grows monotonically and `VACUUM` is never needed on the events table. Each event carries a `stream_id` (the aggregate identifier), a monotonically increasing `sequence` number within that stream, the `event_type`, a JSON `payload`, and a server-assigned `recorded_at` timestamp. A UNIQUE constraint on `(stream_id, sequence)` enforces optimistic concurrency — two concurrent writers racing to append sequence 5 will produce a constraint violation for the loser, which the application retries with the next sequence number. A separate `snapshots` table caches the latest materialised aggregate state so `loadStream()` does not have to replay the full history on every request. Workers serve both the command side (append) and the query side (replay and snapshot) with no intermediate infrastructure.

---

## Schema / Config — D1 migration

```sql
-- migrations/001_event_store.sql

CREATE TABLE IF NOT EXISTS events (
  id          TEXT    NOT NULL DEFAULT (lower(hex(randomblob(16)))),
  stream_id   TEXT    NOT NULL,
  sequence    INTEGER NOT NULL,
  event_type  TEXT    NOT NULL,
  payload     TEXT    NOT NULL, -- JSON
  recorded_at INTEGER NOT NULL DEFAULT (unixepoch('now', 'subsec') * 1000), -- ms
  PRIMARY KEY (id),
  UNIQUE (stream_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_events_stream
  ON events (stream_id, sequence);

-- Snapshot table: one row per stream, updated on every N events
CREATE TABLE IF NOT EXISTS snapshots (
  stream_id   TEXT    NOT NULL PRIMARY KEY,
  sequence    INTEGER NOT NULL, -- sequence of last event included in snapshot
  state       TEXT    NOT NULL, -- JSON serialised aggregate state
  taken_at    INTEGER NOT NULL DEFAULT (unixepoch('now', 'subsec') * 1000)
);
```

```toml
# wrangler.toml
name = "event-store-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[d1_databases]]
binding = "DB"
database_name = "event-store"
database_id = "<d1-database-id>"
```

---

## Implementation — event store core

```typescript
// src/event-store.ts

export interface StoredEvent<T = unknown> {
  id: string;
  streamId: string;
  sequence: number;
  eventType: string;
  payload: T;
  recordedAt: number;
}

export interface AppendResult {
  sequence: number;
  id: string;
}

export class EventStore {
  constructor(private readonly db: D1Database) {}

  /**
   * Append a new event to a stream with optimistic concurrency.
   * `expectedSequence` is the sequence of the last known event;
   * pass -1 for a new stream (first event must be sequence 0).
   * Throws a ConcurrencyError if another writer raced ahead.
   */
  async append<T>(
    streamId: string,
    eventType: string,
    payload: T,
    expectedSequence: number
  ): Promise<AppendResult> {
    const nextSequence = expectedSequence + 1;

    try {
      const result = await this.db
        .prepare(
          `INSERT INTO events (stream_id, sequence, event_type, payload)
           VALUES (?, ?, ?, ?)
           RETURNING id, sequence`
        )
        .bind(streamId, nextSequence, eventType, JSON.stringify(payload))
        .first<{ id: string; sequence: number }>();

      if (!result) throw new Error("INSERT returned no rows");
      return { sequence: result.sequence, id: result.id };
    } catch (err: unknown) {
      if (
        err instanceof Error &&
        err.message.includes("UNIQUE constraint failed")
      ) {
        throw new ConcurrencyError(
          `Stream ${streamId}: sequence ${nextSequence} already exists`
        );
      }
      throw err;
    }
  }

  /**
   * Load all events for a stream starting from `fromSequence`.
   * Pass 0 to load the full stream; pass snapshot.sequence + 1 to
   * load only events after the latest snapshot.
   */
  async loadEvents<T>(
    streamId: string,
    fromSequence = 0
  ): Promise<StoredEvent<T>[]> {
    const { results } = await this.db
      .prepare(
        `SELECT id, stream_id, sequence, event_type, payload, recorded_at
         FROM events
         WHERE stream_id = ? AND sequence >= ?
         ORDER BY sequence ASC`
      )
      .bind(streamId, fromSequence)
      .all<{
        id: string;
        stream_id: string;
        sequence: number;
        event_type: string;
        payload: string;
        recorded_at: number;
      }>();

    return results.map((row) => ({
      id: row.id,
      streamId: row.stream_id,
      sequence: row.sequence,
      eventType: row.event_type,
      payload: JSON.parse(row.payload) as T,
      recordedAt: row.recorded_at,
    }));
  }

  async getSnapshot<S>(
    streamId: string
  ): Promise<{ sequence: number; state: S } | null> {
    const row = await this.db
      .prepare(
        `SELECT sequence, state FROM snapshots WHERE stream_id = ?`
      )
      .bind(streamId)
      .first<{ sequence: number; state: string }>();

    if (!row) return null;
    return { sequence: row.sequence, state: JSON.parse(row.state) as S };
  }

  async saveSnapshot<S>(
    streamId: string,
    sequence: number,
    state: S
  ): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO snapshots (stream_id, sequence, state)
         VALUES (?, ?, ?)
         ON CONFLICT (stream_id)
         DO UPDATE SET sequence = excluded.sequence,
                       state    = excluded.state,
                       taken_at = unixepoch('now', 'subsec') * 1000`
      )
      .bind(streamId, sequence, JSON.stringify(state))
      .run();
  }
}

export class ConcurrencyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConcurrencyError";
  }
}
```

---

## Aggregate replay — loadStream() with snapshot acceleration

```typescript
// src/order-aggregate.ts
import { EventStore, ConcurrencyError } from "./event-store";

// Domain events
type OrderPlaced = { orderId: string; items: string[]; total: number };
type OrderShipped = { trackingCode: string };
type OrderCancelled = { reason: string };
type OrderEvent = OrderPlaced | OrderShipped | OrderCancelled;

export interface OrderState {
  id: string;
  status: "pending" | "shipped" | "cancelled";
  items: string[];
  total: number;
  trackingCode?: string;
  cancelReason?: string;
  version: number; // last applied sequence
}

function applyEvent(state: OrderState, eventType: string, payload: OrderEvent): OrderState {
  switch (eventType) {
    case "OrderPlaced": {
      const p = payload as OrderPlaced;
      return { ...state, status: "pending", items: p.items, total: p.total };
    }
    case "OrderShipped": {
      const p = payload as OrderShipped;
      return { ...state, status: "shipped", trackingCode: p.trackingCode };
    }
    case "OrderCancelled": {
      const p = payload as OrderCancelled;
      return { ...state, status: "cancelled", cancelReason: p.reason };
    }
    default:
      return state;
  }
}

const SNAPSHOT_EVERY = 50; // take a snapshot every 50 events

export async function loadStream(
  store: EventStore,
  orderId: string
): Promise<OrderState> {
  // 1. Load the latest snapshot (may be null for a new stream)
  const snapshot = await store.getSnapshot<OrderState>(orderId);

  const initialState: OrderState = snapshot?.state ?? {
    id: orderId,
    status: "pending",
    items: [],
    total: 0,
    version: -1,
  };

  const fromSequence = snapshot ? snapshot.sequence + 1 : 0;

  // 2. Replay only the events after the snapshot
  const events = await store.loadEvents<OrderEvent>(orderId, fromSequence);

  let state = initialState;
  for (const ev of events) {
    state = applyEvent(state, ev.eventType, ev.payload);
    state = { ...state, version: ev.sequence };
  }

  return state;
}

export async function shipOrder(
  store: EventStore,
  orderId: string,
  trackingCode: string
): Promise<OrderState> {
  const MAX_RETRIES = 3;

  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    const state = await loadStream(store, orderId);

    if (state.status !== "pending") {
      throw new Error(`Cannot ship an order in status: ${state.status}`);
    }

    try {
      const result = await store.append<OrderShipped>(
        orderId,
        "OrderShipped",
        { trackingCode },
        state.version
      );

      const nextState: OrderState = {
        ...state,
        status: "shipped",
        trackingCode,
        version: result.sequence,
      };

      // Save snapshot if we've crossed the threshold
      if (result.sequence % SNAPSHOT_EVERY === 0) {
        await store.saveSnapshot(orderId, result.sequence, nextState);
      }

      return nextState;
    } catch (err) {
      if (err instanceof ConcurrencyError && attempt < MAX_RETRIES - 1) {
        // Another writer raced us — reload and retry
        continue;
      }
      throw err;
    }
  }

  throw new Error("Exceeded max retries due to concurrent writes");
}
```

---

## Anti-patterns

- **Updating or deleting event rows** — the events table is append-only by design; mutations destroy the audit log and break all downstream projections that consumed the original events.
- **Skipping optimistic concurrency checks** — omitting `expectedSequence` and inserting without a sequence check allows two concurrent requests to produce duplicate sequence numbers if the UNIQUE constraint is also missing.
- **Storing very large JSON payloads per event** — D1 rows have a practical limit; store large blobs (files, images) in R2 and reference them by key in the event payload.
- **Replaying the full stream on every command without snapshots** — a stream with thousands of events will hit D1 row-read limits and add latency; snapshot aggressively for high-frequency aggregates.

---

## Gotchas

- `unixepoch('now', 'subsec') * 1000` gives millisecond precision in SQLite; plain `unixepoch()` gives only second precision and is insufficient to sort events within a burst.
- D1's `batch()` API sends multiple statements in a single HTTP round-trip; use it when appending multiple events atomically in a saga, but note that D1 batch statements run in a single transaction.
- The UNIQUE constraint on `(stream_id, sequence)` is enforced at the database level, but a Worker retry loop must catch `ConcurrencyError` and re-load the aggregate before retrying — never blindly increment the sequence.
- `RETURNING id, sequence` requires D1's SQLite version to support the `RETURNING` clause; verify with `wrangler d1 execute --command "SELECT sqlite_version()"`.

---

## Verification

```bash
# Apply the migration
wrangler d1 migrations apply event-store --remote

# Append a test event
wrangler d1 execute event-store --remote \
  --command "
    INSERT INTO events (stream_id, sequence, event_type, payload)
    VALUES ('order-001', 0, 'OrderPlaced',
            '{\"orderId\":\"order-001\",\"items\":[\"SKU-1\"],\"total\":99}');
  "

# Replay the stream
wrangler d1 execute event-store --remote \
  --command "SELECT sequence, event_type, payload FROM events WHERE stream_id='order-001' ORDER BY sequence ASC"

# Confirm concurrency: insert sequence 0 again — must fail
wrangler d1 execute event-store --remote \
  --command "
    INSERT INTO events (stream_id, sequence, event_type, payload)
    VALUES ('order-001', 0, 'OrderPlaced', '{}');
  "
# Expected: Error: UNIQUE constraint failed: events.stream_id, events.sequence
```

---

## Related

- `pipes-filters-workers-queues-pipeline.md`
- `shared-nothing-workers-stateless-design.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Event Sourcing pattern (Martin Fowler) — https://martinfowler.com/eaaDev/EventSourcing.html
- Greg Young — CQRS and Event Sourcing — https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
