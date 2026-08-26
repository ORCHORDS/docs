# Event Sourcing with D1 as the Append-Only Event Store

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

---

## Symptom / Use-case

You need a full audit trail of everything that happens in your application — not just the current state but every mutation that led to it. You want to replay history to rebuild projections, debug anomalies, or migrate to new read models without losing historical fidelity. Your stack is Cloudflare Workers + D1, and you want to avoid managing a separate Kafka cluster or a dedicated event-store service.

---

## Context

Event sourcing stores state changes as an immutable, ordered sequence of events rather than overwriting rows. The current state of any aggregate is derived by replaying all events for that aggregate ID. D1 (Cloudflare's serverless SQLite) is a natural fit for a small-to-medium event store:

- SQLite's `ROWID` gives a monotonically increasing, per-database sequence number with no extra setup.
- D1's `batch()` API lets you atomically append an event and update a sequence pointer in one round-trip.
- D1's read replicas (when enabled) let projections read from a nearby replica without hitting the write endpoint.
- The immutability guarantee is enforced by never issuing `UPDATE` or `DELETE` against the events table.

The pattern becomes powerful when combined with Durable Objects for aggregate-level optimistic concurrency (see `event-sourcing-cqrs-patterns.md`) or with Cloudflare Queues to fan events out to projectors asynchronously.

---

## Event Store Schema

```sql
-- events.sql  (run once via wrangler d1 execute)
CREATE TABLE IF NOT EXISTS domain_events (
  -- Monotonic sequence; ROWID alias gives free integer primary key
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  -- Logical stream identifier: e.g. "order:abc123"
  stream_id    TEXT    NOT NULL,
  -- Optimistic concurrency: position within this stream (0-based)
  stream_seq   INTEGER NOT NULL,
  -- Event type, used by projectors to decide handler
  event_type   TEXT    NOT NULL,
  -- Arbitrary JSON payload; keep ≤8 KB for best D1 performance
  payload      TEXT    NOT NULL DEFAULT '{}',
  -- RFC 3339 wall-clock timestamp, set by the writer
  occurred_at  TEXT    NOT NULL,
  -- Causation and correlation IDs for distributed tracing
  causation_id TEXT,
  correlation_id TEXT,
  -- Prevent duplicate writes from retries
  idempotency_key TEXT UNIQUE,

  -- Enforce stream ordering: no two events in same stream at same position
  UNIQUE (stream_id, stream_seq)
);

-- Index for replaying a single stream in order
CREATE INDEX IF NOT EXISTS idx_events_stream
  ON domain_events (stream_id, stream_seq);

-- Index for global ordered read (checkpoint-based projectors)
CREATE INDEX IF NOT EXISTS idx_events_seq
  ON domain_events (seq);
```

The `UNIQUE (stream_id, stream_seq)` constraint is the concurrency guard: if two Workers race to append event #5 to the same stream, the second insert fails with a UNIQUE constraint violation, and the caller retries with the current version.

---

## Appending Events in a Worker

```typescript
// src/event-store.ts
export interface DomainEvent {
  streamId: string;
  streamSeq: number;         // Expected next position (optimistic lock)
  eventType: string;
  payload: unknown;
  occurredAt: string;
  causationId?: string;
  correlationId?: string;
  idempotencyKey?: string;
}

export class EventStore {
  constructor(private db: D1Database) {}

  /**
   * Append a single event to a stream.
   * Throws if streamSeq is already taken (concurrent write detected).
   */
  async append(event: DomainEvent): Promise<number> {
    const stmt = this.db.prepare(`
      INSERT INTO domain_events
        (stream_id, stream_seq, event_type, payload,
         occurred_at, causation_id, correlation_id, idempotency_key)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);

    const result = await stmt.bind(
      event.streamId,
      event.streamSeq,
      event.eventType,
      JSON.stringify(event.payload),
      event.occurredAt,
      event.causationId ?? null,
      event.correlationId ?? null,
      event.idempotencyKey ?? null,
    ).run();

    if (!result.success) {
      throw new Error(`Append failed for stream ${event.streamId}`);
    }
    // result.meta.last_row_id is the global seq assigned by D1
    return result.meta.last_row_id as number;
  }

  /**
   * Append multiple events atomically in a batch.
   * All-or-nothing: D1 batch() wraps statements in an implicit transaction.
   */
  async appendBatch(events: DomainEvent[]): Promise<void> {
    const stmts = events.map(e =>
      this.db.prepare(`
        INSERT INTO domain_events
          (stream_id, stream_seq, event_type, payload,
           occurred_at, causation_id, correlation_id, idempotency_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(
        e.streamId, e.streamSeq, e.eventType, JSON.stringify(e.payload),
        e.occurredAt, e.causationId ?? null, e.correlationId ?? null,
        e.idempotencyKey ?? null,
      )
    );
    await this.db.batch(stmts);
  }
}
```

---

## Reading and Replaying a Stream

```typescript
// src/event-store.ts (continued)

export interface StoredEvent extends DomainEvent {
  seq: number;
}

export class EventStore {
  // ... append methods above

  /** Replay all events for a stream in order. */
  async loadStream(streamId: string, fromSeq = 0): Promise<StoredEvent[]> {
    const result = await this.db.prepare(`
      SELECT seq, stream_id, stream_seq, event_type, payload,
             occurred_at, causation_id, correlation_id, idempotency_key
      FROM   domain_events
      WHERE  stream_id = ?
        AND  stream_seq >= ?
      ORDER  BY stream_seq ASC
    `).bind(streamId, fromSeq).all<Record<string, unknown>>();

    return (result.results ?? []).map(row => ({
      seq:            Number(row.seq),
      streamId:       row.stream_id as string,
      streamSeq:      Number(row.stream_seq),
      eventType:      row.event_type as string,
      payload:        JSON.parse(row.payload as string),
      occurredAt:     row.occurred_at as string,
      causationId:    row.causation_id as string | undefined,
      correlationId:  row.correlation_id as string | undefined,
      idempotencyKey: row.idempotency_key as string | undefined,
    }));
  }

  /** Read all events globally after a checkpoint (for projectors). */
  async readAfterCheckpoint(
    afterSeq: number,
    limit = 500,
  ): Promise<StoredEvent[]> {
    const result = await this.db.prepare(`
      SELECT seq, stream_id, stream_seq, event_type, payload,
             occurred_at, causation_id, correlation_id, idempotency_key
      FROM   domain_events
      WHERE  seq > ?
      ORDER  BY seq ASC
      LIMIT  ?
    `).bind(afterSeq, limit).all<Record<string, unknown>>();

    return (result.results ?? []).map(row => ({
      seq:           Number(row.seq),
      streamId:      row.stream_id as string,
      streamSeq:     Number(row.stream_seq),
      eventType:     row.event_type as string,
      payload:       JSON.parse(row.payload as string),
      occurredAt:    row.occurred_at as string,
      causationId:   (row.causation_id as string) ?? undefined,
      correlationId: (row.correlation_id as string) ?? undefined,
    }));
  }
}
```

---

## Projector Checkpoint Pattern

A projector reads the global event stream and builds a read model (e.g. a `orders_summary` table). It persists a checkpoint so it can resume after a restart without replaying the entire store.

```typescript
// src/projectors/order-summary-projector.ts
export class OrderSummaryProjector {
  constructor(
    private store: EventStore,
    private db: D1Database,
  ) {}

  async run(): Promise<void> {
    // Load last processed global seq from a checkpoints table
    const cpRow = await this.db
      .prepare(`SELECT last_seq FROM projector_checkpoints WHERE name = ?`)
      .bind('order_summary')
      .first<{ last_seq: number }>();

    let checkpoint = cpRow?.last_seq ?? 0;

    while (true) {
      const events = await this.store.readAfterCheckpoint(checkpoint, 500);
      if (events.length === 0) break;

      // Build up batch of read-model writes + checkpoint update
      const stmts: D1PreparedStatement[] = [];

      for (const event of events) {
        if (event.eventType === 'OrderPlaced') {
          const p = event.payload as {
            orderId: string; customerId: string; totalCents: number;
          };
          stmts.push(
            this.db.prepare(`
              INSERT INTO orders_summary (order_id, customer_id, total_cents, status, placed_at)
              VALUES (?, ?, ?, 'placed', ?)
              ON CONFLICT (order_id) DO NOTHING
            `).bind(p.orderId, p.customerId, p.totalCents, event.occurredAt)
          );
        } else if (event.eventType === 'OrderShipped') {
          const p = event.payload as { orderId: string };
          stmts.push(
            this.db.prepare(`
              UPDATE orders_summary SET status = 'shipped' WHERE order_id = ?
            `).bind(p.orderId)
          );
        }
      }

      // Update checkpoint to last processed seq
      checkpoint = events[events.length - 1].seq;
      stmts.push(
        this.db.prepare(`
          INSERT INTO projector_checkpoints (name, last_seq)
          VALUES (?, ?)
          ON CONFLICT (name) DO UPDATE SET last_seq = excluded.last_seq
        `).bind('order_summary', checkpoint)
      );

      await this.db.batch(stmts);
    }
  }
}
```

The projector checkpoint table:

```sql
CREATE TABLE IF NOT EXISTS projector_checkpoints (
  name     TEXT PRIMARY KEY,
  last_seq INTEGER NOT NULL DEFAULT 0
);
```

---

## Snapshot Strategy

Full replay from seq=0 becomes expensive as a stream grows. Take a snapshot of aggregate state every N events (e.g. every 50):

```typescript
// src/snapshots.ts
export async function saveSnapshot(
  db: D1Database,
  streamId: string,
  atSeq: number,         // stream_seq of the last event included
  state: unknown,
): Promise<void> {
  await db.prepare(`
    INSERT INTO aggregate_snapshots (stream_id, at_stream_seq, state, taken_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (stream_id)
    DO UPDATE SET at_stream_seq = excluded.at_stream_seq,
                  state = excluded.state,
                  taken_at = excluded.taken_at
    WHERE excluded.at_stream_seq > aggregate_snapshots.at_stream_seq
  `).bind(streamId, atSeq, JSON.stringify(state), new Date().toISOString()).run();
}

export async function loadSnapshot(
  db: D1Database,
  streamId: string,
): Promise<{ atStreamSeq: number; state: unknown } | null> {
  const row = await db.prepare(`
    SELECT at_stream_seq, state FROM aggregate_snapshots WHERE stream_id = ?
  `).bind(streamId).first<{ at_stream_seq: number; state: string }>();

  if (!row) return null;
  return { atStreamSeq: row.at_stream_seq, state: JSON.parse(row.state) };
}
```

```sql
CREATE TABLE IF NOT EXISTS aggregate_snapshots (
  stream_id      TEXT PRIMARY KEY,
  at_stream_seq  INTEGER NOT NULL,
  state          TEXT    NOT NULL,
  taken_at       TEXT    NOT NULL
);
```

When loading an aggregate, first attempt to load the snapshot, then replay only events after `at_stream_seq`.

---

## Anti-patterns

- **Mutating events**: Never `UPDATE` or `DELETE` rows in `domain_events`. If a business correction is needed, append a compensating event (e.g. `OrderCancelled`, `AmountCorrected`).
- **Storing derived state in the event payload**: Events should record what happened, not what the current state is. Avoid embedding computed fields like `newBalance` inside `AccountCredited` — the projector recomputes that.
- **Fat events**: Payloads above ~8 KB hurt D1 row read performance. Store large blobs in R2 and put only the R2 key in the event payload.
- **Long-running projector in a single Worker invocation**: D1 queries are subject to the Worker CPU and wall-clock limits. Run projectors in scheduled Workers (Cron Triggers) or via Queues, processing bounded batches per invocation.
- **Missing idempotency keys on appends from at-least-once delivery**: Without the `idempotency_key UNIQUE` constraint, a retry after a network timeout will duplicate the event. Always generate a stable key (e.g. `sha256(requestId + streamId + streamSeq)`).
- **Global table scan for streams**: Querying `WHERE stream_id = ?` without the index `(stream_id, stream_seq)` forces a full table scan that degrades as the event log grows.

---

## Gotchas

- **D1 is SQLite, not Postgres**: SQLite's `AUTOINCREMENT` keyword is distinct from implicit `ROWID`. Use `INTEGER PRIMARY KEY AUTOINCREMENT` to prevent the `ROWID` from being reused after a deletion (even though you should never delete events, defensive coding helps).
- **D1 read replicas may lag**: When a projector reads from a read replica immediately after an append, it may not see the latest events. Always use the primary endpoint for projectors that need linearizability, or tolerate the replica lag (typically <1 s) with a brief retry.
- **SQLite `UNIQUE` constraint violation error code**: D1 returns an HTTP 500 with a SQLite error code `SQLITE_CONSTRAINT_UNIQUE` (19). Parse the error message to distinguish a concurrency conflict (stream_seq collision) from a true server error.
- **D1 batch size limits**: D1 batches accept up to 100 statements per call. Chunk large projector writes accordingly.
- **Time ordering vs. seq ordering**: `occurred_at` is a wall-clock string set by the appending Worker, which can skew across Workers. Always use `seq` (the AUTOINCREMENT column) for ordering, never `occurred_at`.

---

## Verification

```bash
# 1. Schema deployed
wrangler d1 execute MY_DB --command \
  "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"

# 2. Append a test event and check seq
wrangler d1 execute MY_DB --command \
  "INSERT INTO domain_events (stream_id, stream_seq, event_type, payload, occurred_at)
   VALUES ('order:test-1', 0, 'OrderPlaced', '{\"orderId\":\"test-1\"}', datetime('now'));"

wrangler d1 execute MY_DB --command \
  "SELECT seq, stream_id, stream_seq, event_type FROM domain_events ORDER BY seq DESC LIMIT 5;"

# 3. Verify concurrency guard (second insert at same stream_seq must fail)
wrangler d1 execute MY_DB --command \
  "INSERT INTO domain_events (stream_id, stream_seq, event_type, payload, occurred_at)
   VALUES ('order:test-1', 0, 'Duplicate', '{}', datetime('now'));"
# Expect: UNIQUE constraint failed: domain_events.stream_id, domain_events.stream_seq

# 4. Idempotency key prevents duplicate on retry
wrangler d1 execute MY_DB --command \
  "INSERT OR IGNORE INTO domain_events
     (stream_id, stream_seq, event_type, payload, occurred_at, idempotency_key)
   VALUES ('order:test-1', 1, 'OrderShipped', '{}', datetime('now'), 'idem-key-abc');"
# Insert twice with same key — second is silently ignored
```

---

## Related

- `event-sourcing-cqrs-patterns.md` — combining event sourcing with CQRS read models
- `event-sourcing-projections-snapshots.md` — projection lifecycle and snapshot strategies
- `cqrs-cloudflare-workers-d1.md` — Workers-specific CQRS with D1 read models
- `idempotency-keys-workers-api.md` — idempotency key generation and enforcement
- `workers-queue-fanout-architecture.md` — fanning events to projectors via Cloudflare Queues
- `outbox-pattern.md` — reliable event publishing from within a transaction boundary

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- D1 batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Martin Fowler — Event Sourcing pattern — https://martinfowler.com/eaaDev/EventSourcing.html
- Greg Young — CQRS and Event Sourcing — https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
- SQLite AUTOINCREMENT semantics — https://www.sqlite.org/autoinc.html
