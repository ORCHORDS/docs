# D1 WAL Mode and Checkpoint Tuning for Write-Heavy Workloads

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A D1 database ingests high-frequency writes — event tracking, audit logs, leaderboard
updates — and begins exhibiting elevated P99 write latency (>200 ms) under sustained
load. `EXPLAIN QUERY PLAN` shows no bad index choices; the bottleneck is lock contention
at the SQLite page level, not the query planner. Write throughput plateaus around
80–120 rows/s even with batch inserts.

## Context

D1 uses SQLite under the hood with WAL (Write-Ahead Log) mode enabled by default on
new databases. WAL mode decouples readers from writers, allowing concurrent reads while
a write transaction is in progress. However, WAL files grow until a checkpoint is
triggered, and large un-checkpointed WAL files degrade both read and write performance
because every read must scan the WAL for the latest page version. Tuning checkpoint
frequency, transaction granularity, and write batching recovers substantial throughput.

## Confirm WAL Mode is Active

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { results } = await env.DB.prepare('PRAGMA journal_mode').all();
    // Expect: [{ journal_mode: 'wal' }]
    // If 'delete', contact Cloudflare support — old databases may use rollback journal

    const { results: walStatus } = await env.DB.prepare(
      'PRAGMA wal_checkpoint(PASSIVE)',
    ).all();
    // Returns: [{ busy, log, checkpointed }]
    // If log >> checkpointed, WAL is not being flushed — checkpoint manually

    return Response.json({ results, walStatus });
  },
};
```

## Explicit Checkpoint to Flush WAL Backlog

Run a checkpoint in a low-traffic window (e.g., a Cron Trigger) to prevent WAL
accumulation from degrading read latency.

```typescript
// src/maintenance.ts
export async function runCheckpoint(db: D1Database): Promise<void> {
  // TRUNCATE mode resets the WAL file to zero bytes after checkpointing
  // More aggressive than PASSIVE; blocks until all readers release
  const result = await db.prepare('PRAGMA wal_checkpoint(TRUNCATE)').first<{
    busy: number;
    log: number;
    checkpointed: number;
  }>();

  if (result && result.busy > 0) {
    console.warn('Checkpoint blocked by active readers:', result);
  } else {
    console.log(`Checkpointed ${result?.checkpointed} pages`);
  }
}

// wrangler.toml cron: "*/15 * * * *"  (every 15 minutes)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await runCheckpoint(env.DB);
  },
};
```

## Maximising Write Throughput with `batch()`

Each `db.prepare().run()` call is its own auto-commit transaction. At scale, the
overhead of individual transaction WAL entries dominates. Group writes into a single
`db.batch()` call so they land in one WAL transaction.

```typescript
async function bulkInsertEvents(
  db: D1Database,
  events: Array<{ id: string; type: string; ts: number; payload: string }>,
): Promise<void> {
  const CHUNK = 100; // D1 batch limit per call

  for (let i = 0; i < events.length; i += CHUNK) {
    const slice = events.slice(i, i + CHUNK);
    await db.batch(
      slice.map((e) =>
        db.prepare(
          'INSERT INTO events (id, type, ts, payload) VALUES (?, ?, ?, ?)',
        ).bind(e.id, e.type, e.ts, e.payload),
      ),
    );
  }
}
```

## Auto-Vacuum to Reclaim Freed Pages

Deleted rows leave dead pages in the B-tree that bloat the file and slow WAL
checkpoints. Enable incremental auto-vacuum on insert-heavy + delete-heavy tables.

```sql
-- Run once during schema migration
PRAGMA auto_vacuum = INCREMENTAL;
PRAGMA incremental_vacuum(100); -- reclaim up to 100 pages per call
```

```typescript
// Maintenance cron: reclaim pages after bulk deletes
async function incrementalVacuum(db: D1Database, pages = 200): Promise<void> {
  await db.prepare(`PRAGMA incremental_vacuum(${pages})`).run();
}
```

## Measuring WAL Size and Write Amplification

```typescript
async function walDiagnostics(db: D1Database): Promise<Record<string, number>> {
  const [pageSize, walPages, dbPages] = await Promise.all([
    db.prepare('PRAGMA page_size').first<{ page_size: number }>(),
    db.prepare('PRAGMA wal_checkpoint(PASSIVE)').first<{ log: number; checkpointed: number }>(),
    db.prepare('PRAGMA page_count').first<{ page_count: number }>(),
  ]);

  return {
    pageSizeBytes: pageSize?.page_size ?? 0,
    walPages: walPages?.log ?? 0,
    checkpointedPages: walPages?.checkpointed ?? 0,
    dbPages: dbPages?.page_count ?? 0,
    walRatio: (walPages?.log ?? 0) / Math.max(dbPages?.page_count ?? 1, 1),
  };
  // walRatio > 0.5 means WAL is nearly as large as the DB — checkpoint urgently
}
```

## Anti-patterns

- **Issuing `PRAGMA wal_checkpoint(FULL)` on the hot path** — FULL blocks all writers
  until the checkpoint completes; use PASSIVE on the hot path or TRUNCATE in scheduled
  maintenance.
- **100 % individual `run()` calls for bulk ingestion** — each is its own WAL entry;
  100 separate inserts are ~10× slower than one `batch()` of 100.
- **Enabling `PRAGMA synchronous = OFF`** — D1 manages durability at the distributed
  layer; this PRAGMA is a no-op or may conflict with D1's internal replication.
- **Skipping `PRAGMA auto_vacuum` on event/log tables** — without it, a table that
  accumulates and purges rows will bloat the file indefinitely.

## Gotchas

- `wal_checkpoint(TRUNCATE)` returns `busy > 0` when readers hold open transactions.
  Schedule checkpoints during off-peak rather than retrying in a tight loop.
- D1 does not expose the raw WAL file; WAL diagnostics must be inferred from
  `wal_checkpoint(PASSIVE)` output (log vs. checkpointed page counts).
- `db.batch()` is atomic — if any statement fails, the entire batch is rolled back.
  Split heterogeneous writes (different tables) into separate batches if partial
  success is acceptable.
- Write throughput limits are also gated by D1's per-database write concurrency limits
  (one writer at a time per SQLite file). Horizontal sharding across multiple D1
  databases is the only way to exceed that ceiling.

## Verification

```bash
# Tail Workers logs for checkpoint diagnostics
wrangler tail --format=json | jq 'select(.logs[].message | test("Checkpointed|walRatio"))'

# Query the D1 meta table for row counts after bulk insert
wrangler d1 execute MY_DB --command "SELECT COUNT(*) FROM events"

# Measure P99 write latency before and after batching changes
wrangler d1 execute MY_DB --command "PRAGMA wal_checkpoint(PASSIVE)"
```

## Related

- `d1-batch-query-performance-optimization.md` — batch read strategies
- `d1-prepared-statement-reuse.md` — reducing parse overhead per write
- `d1-transaction-retry-optimistic-locking.md` — handling write conflicts
- `d1-without-rowid-table-read-performance.md` — alternative table formats

## Sources

- SQLite WAL documentation: https://www.sqlite.org/wal.html
- Cloudflare D1 Docs: https://developers.cloudflare.com/d1/
- SQLite checkpoint modes: https://www.sqlite.org/pragma.html#pragma_wal_checkpoint
