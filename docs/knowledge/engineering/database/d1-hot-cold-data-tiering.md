# D1 Data Archival and Hot/Cold Storage Tiering

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your D1 database is growing faster than expected. A `messages` or `events` table
accumulates millions of rows, but 95% of queries touch data from the last 30 days.
Old data inflates query scan times, bloats the D1 database file, and pushes you
toward D1's storage limits (currently 10 GB per database in the paid plan).

You need an archival strategy that:
- Moves cold data out of the hot D1 database without application downtime.
- Keeps cold data queryable when needed (compliance, analytics, exports).
- Runs as a background Cloudflare Worker (Cron Trigger) rather than a manual process.

## Context

D1 does not have built-in partitioning or automatic archival. The pattern requires:

1. **Hot table** — recent data, lives in the primary D1 database, queried on every
   request.
2. **Cold store** — archived rows. Options:
   - A second D1 database (lower query frequency, same SQL interface).
   - Cloudflare R2 (object storage, CSV/NDJSON exports, queryable via Workers AI
     or DuckDB in a sidecar).
   - Cloudflare Analytics Engine (append-only, for event/metric data).
3. **Archival Worker** — a Cron Trigger Worker that runs nightly, moves rows older
   than a threshold, and deletes them from the hot database.

The two-database approach (hot D1 + cold D1) keeps data queryable via the same
SQL interface. The R2 approach is better for bulk exports and offline analytics.

## Schema Design

```sql
-- HOT DATABASE: primary D1 (hot-db binding)
CREATE TABLE events (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  event_type  TEXT NOT NULL,
  payload     TEXT,             -- JSON
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Index for archival scan: newest rows first, by tenant
CREATE INDEX idx_events_created ON events(created_at);
CREATE INDEX idx_events_tenant_created ON events(tenant_id, created_at);

-- Archival tracking: records which batches have been archived
CREATE TABLE archival_log (
  id           TEXT PRIMARY KEY,
  archived_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  rows_moved   INTEGER NOT NULL,
  cutoff_ts    INTEGER NOT NULL,   -- unixepoch() of the oldest row archived
  status       TEXT NOT NULL DEFAULT 'success'
);
```

```sql
-- COLD DATABASE: secondary D1 (cold-db binding) — identical schema
CREATE TABLE events (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  event_type  TEXT NOT NULL,
  payload     TEXT,
  created_at  INTEGER NOT NULL,
  archived_at INTEGER NOT NULL DEFAULT (unixepoch())  -- extra: when it was archived
);

CREATE INDEX idx_cold_events_tenant_created ON events(tenant_id, created_at);
```

## Archival Worker (Cron Trigger)

```typescript
// src/workers/archival-worker.ts
import { D1Database } from '@cloudflare/workers-types';

interface Env {
  HOT_DB:  D1Database;
  COLD_DB: D1Database;
}

const ARCHIVE_OLDER_THAN_DAYS = 30;
const BATCH_SIZE = 500;          // rows per iteration
const MAX_ITERATIONS = 20;       // cap to stay within CPU time limit

export default {
  /**
   * Scheduled handler — runs on cron schedule defined in wrangler.toml
   * e.g. crons = ["0 3 * * *"]  (daily at 03:00 UTC)
   */
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runArchival(env));
  },

  // Also expose as fetch for manual triggering (admin-only endpoint)
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }
    ctx.waitUntil(runArchival(env));
    return new Response(JSON.stringify({ status: 'archival started' }), {
      headers: { 'content-type': 'application/json' },
    });
  },
};

async function runArchival(env: Env): Promise<void> {
  const cutoffTs = Math.floor(Date.now() / 1000) - ARCHIVE_OLDER_THAN_DAYS * 86400;
  let totalMoved = 0;

  for (let i = 0; i < MAX_ITERATIONS; i++) {
    const moved = await archiveBatch(env.HOT_DB, env.COLD_DB, cutoffTs);
    totalMoved += moved;
    if (moved < BATCH_SIZE) break;  // No more rows to archive
    // Small yield to avoid hitting the CPU limit in a tight loop
    await new Promise((r) => setTimeout(r, 10));
  }

  // Record the archival run
  await env.HOT_DB
    .prepare('INSERT INTO archival_log (id, rows_moved, cutoff_ts) VALUES (?, ?, ?)')
    .bind(crypto.randomUUID(), totalMoved, cutoffTs)
    .run();

  console.log(`Archival complete: ${totalMoved} rows moved, cutoff=${new Date(cutoffTs * 1000).toISOString()}`);
}

/**
 * Moves one batch of cold rows from HOT_DB to COLD_DB.
 * Returns the number of rows moved (0 = done).
 *
 * Strategy: SELECT → INSERT INTO cold → DELETE from hot, inside a transaction
 * on each database. Because D1 does not support cross-database transactions,
 * we accept a small risk of duplication (cold insert succeeds, hot delete fails).
 * The cold table's PRIMARY KEY prevents true duplicates; re-running is idempotent.
 */
async function archiveBatch(
  hot: D1Database,
  cold: D1Database,
  cutoffTs: number,
): Promise<number> {
  // Read the batch from hot
  const rows = await hot
    .prepare(`
      SELECT id, tenant_id, event_type, payload, created_at
      FROM events
      WHERE created_at < ?
      ORDER BY created_at
      LIMIT ?
    `)
    .bind(cutoffTs, BATCH_SIZE)
    .all<{
      id: string;
      tenant_id: string;
      event_type: string;
      payload: string | null;
      created_at: number;
    }>();

  if (rows.results.length === 0) return 0;

  const now = Math.floor(Date.now() / 1000);

  // Insert into cold (idempotent via INSERT OR IGNORE)
  const coldInserts = rows.results.map((row) =>
    cold
      .prepare(
        'INSERT OR IGNORE INTO events (id, tenant_id, event_type, payload, created_at, archived_at) VALUES (?, ?, ?, ?, ?, ?)',
      )
      .bind(row.id, row.tenant_id, row.event_type, row.payload, row.created_at, now),
  );

  await cold.batch(coldInserts);

  // Delete from hot (only the IDs we just archived)
  const ids = rows.results.map((r) => r.id);
  const placeholders = ids.map(() => '?').join(', ');
  await hot.prepare(`DELETE FROM events WHERE id IN (${placeholders})`).bind(...ids).run();

  return rows.results.length;
}
```

```toml
# wrangler.toml
[triggers]
crons = ["0 3 * * *"]   # daily at 03:00 UTC

[[d1_databases]]
binding = "HOT_DB"
database_name = "events-hot"
database_id = "..."

[[d1_databases]]
binding = "COLD_DB"
database_name = "events-cold"
database_id = "..."
```

## Querying Cold Data

```typescript
// src/services/event-service.ts
import { D1Database } from '@cloudflare/workers-types';

interface EventQueryOptions {
  tenantId: string;
  from: Date;
  to: Date;
  limit?: number;
}

/**
 * Unified query: searches hot DB first, falls back to cold DB for older ranges.
 * For date ranges that span the hot/cold boundary, executes both and merges.
 */
export async function queryEvents(
  hot: D1Database,
  cold: D1Database,
  opts: EventQueryOptions,
) {
  const { tenantId, from, to, limit = 100 } = opts;
  const fromTs = Math.floor(from.getTime() / 1000);
  const toTs   = Math.floor(to.getTime() / 1000);
  const ARCHIVE_BOUNDARY = Math.floor(Date.now() / 1000) - 30 * 86400;

  const queryFor = (db: D1Database) =>
    db
      .prepare(`
        SELECT id, event_type, payload, created_at
        FROM events
        WHERE tenant_id = ?
          AND created_at BETWEEN ? AND ?
        ORDER BY created_at DESC
        LIMIT ?
      `)
      .bind(tenantId, fromTs, toTs, limit)
      .all<{ id: string; event_type: string; payload: string; created_at: number }>();

  if (toTs < ARCHIVE_BOUNDARY) {
    // Entirely in cold range
    return (await queryFor(cold)).results;
  }

  if (fromTs >= ARCHIVE_BOUNDARY) {
    // Entirely in hot range
    return (await queryFor(hot)).results;
  }

  // Spans both: query in parallel and merge
  const [hotRows, coldRows] = await Promise.all([queryFor(hot), queryFor(cold)]);
  const merged = [...hotRows.results, ...coldRows.results];
  merged.sort((a, b) => b.created_at - a.created_at);
  return merged.slice(0, limit);
}
```

## R2 Export Alternative (Bulk Archival)

For analytics workloads where SQL queries on cold data are not required:

```typescript
// src/workers/r2-archival-worker.ts
import { D1Database, R2Bucket } from '@cloudflare/workers-types';

interface Env {
  HOT_DB: D1Database;
  ARCHIVE_BUCKET: R2Bucket;
}

export async function exportToR2(env: Env, cutoffTs: number): Promise<void> {
  const rows = await env.HOT_DB
    .prepare('SELECT * FROM events WHERE created_at < ? ORDER BY created_at')
    .bind(cutoffTs)
    .all();

  if (rows.results.length === 0) return;

  // NDJSON format: one JSON object per line, efficient for streaming reads
  const ndjson = rows.results
    .map((row) => JSON.stringify(row))
    .join('\n');

  const date = new Date(cutoffTs * 1000).toISOString().slice(0, 10);
  const key = `events/year=${date.slice(0, 4)}/month=${date.slice(5, 7)}/day=${date.slice(8, 10)}/events-${cutoffTs}.ndjson`;

  await env.ARCHIVE_BUCKET.put(key, ndjson, {
    httpMetadata: { contentType: 'application/x-ndjson' },
    customMetadata: {
      row_count: String(rows.results.length),
      cutoff_ts: String(cutoffTs),
    },
  });

  // Delete archived rows from hot
  const ids = (rows.results as { id: string }[]).map((r) => r.id);
  const placeholders = ids.map(() => '?').join(', ');
  await env.HOT_DB
    .prepare(`DELETE FROM events WHERE id IN (${placeholders})`)
    .bind(...ids)
    .run();
}
```

## Monitoring Archival Health

```sql
-- Check archival log: recent runs and row counts
SELECT
  id,
  datetime(archived_at, 'unixepoch') AS archived_at,
  rows_moved,
  datetime(cutoff_ts, 'unixepoch') AS cutoff,
  status
FROM archival_log
ORDER BY archived_at DESC
LIMIT 10;

-- Check hot DB size pressure: oldest row vs expected cutoff
SELECT
  MIN(created_at) AS oldest_row_ts,
  datetime(MIN(created_at), 'unixepoch') AS oldest_row_date,
  COUNT(*) AS total_rows
FROM events;

-- Rows by age bucket (diagnose retention)
SELECT
  CASE
    WHEN created_at > unixepoch() - 7*86400   THEN '0-7 days'
    WHEN created_at > unixepoch() - 30*86400  THEN '7-30 days'
    WHEN created_at > unixepoch() - 90*86400  THEN '30-90 days'
    ELSE '90+ days'
  END AS age_bucket,
  COUNT(*) AS row_count
FROM events
GROUP BY age_bucket
ORDER BY MIN(created_at);
```

## Anti-patterns

- **Running archival synchronously inside a user request**: Archival is slow and must
  run in the background via Cron Trigger or `ctx.waitUntil()`.
- **Deleting rows before confirming cold insert**: Always insert into cold first.
  If the cold insert fails, retry — the hot row is still safe. Deleting before
  confirming results in data loss.
- **Using a single transaction across two D1 databases**: D1 does not support
  cross-database transactions. Use `INSERT OR IGNORE` in cold and accept that a
  crash between insert and delete leaves a duplicate in cold (idempotent by PK).
- **Archiving without a batch size limit**: Archiving 100 000 rows in one operation
  will exceed D1's batch statement limit (currently 100 statements per batch) and
  the Worker's CPU time limit. Always use `LIMIT` and loop.
- **Ignoring the cold DB in user-facing queries for date ranges that span the
  boundary**: Users see missing data if they search a 60-day range when the boundary
  is at 30 days.

## Gotchas

- D1 batch operations accept up to 100 prepared statements per `.batch()` call.
  Keep `BATCH_SIZE` at or below this limit when using `batch()` for cold inserts.
- Cloudflare Worker Cron Triggers have a 30-second CPU time limit (free) and
  30-minute wall time limit (paid). For very large archives, run multiple small
  batches and track progress in a KV key.
- D1's `VACUUM` command reclaims space after deletes. In SQLite, deleted rows leave
  gaps in the file. D1 runs VACUUM automatically on a schedule, but large deletes
  may not immediately reduce reported storage.
- If you use `created_at` as the archive boundary, rows inserted with incorrect
  timestamps (clock skew, backdated imports) may be archived too early or never.
  Add a `received_at` column set by the server for a reliable boundary.

## Verification

```typescript
// Verify idempotency: re-running archival on already-archived rows
async function verifyIdempotency(hot: D1Database, cold: D1Database, cutoffTs: number) {
  const hotBefore = await hot.prepare('SELECT COUNT(*) AS n FROM events WHERE created_at < ?')
    .bind(cutoffTs).first<{ n: number }>();

  // Run archival twice
  await archiveBatch(hot, cold, cutoffTs);
  await archiveBatch(hot, cold, cutoffTs);

  const hotAfter = await hot.prepare('SELECT COUNT(*) AS n FROM events WHERE created_at < ?')
    .bind(cutoffTs).first<{ n: number }>();

  console.assert(hotAfter!.n === 0, 'Hot DB still has rows past cutoff');

  const coldCount = await cold.prepare('SELECT COUNT(*) AS n FROM events WHERE created_at < ?')
    .bind(cutoffTs).first<{ n: number }>();

  console.assert(coldCount!.n === hotBefore!.n, 'Cold DB row count mismatch');
}
```

## Related

- `archive-table-patterns.md` — generic SQL archival table patterns
- `d1-batch-operations-performance.md` — D1 batch API limits and performance
- `d1-time-series-partitioning.md` — partitioning time-series data in D1
- `data-retention-deletion.md` — GDPR-compliant data deletion strategies
- `database-backup-strategies.md` — D1 point-in-time recovery options

## Sources

- Cloudflare D1 limits: developers.cloudflare.com/d1/platform/limits
- Cloudflare Cron Triggers: developers.cloudflare.com/workers/configuration/cron-triggers
- Cloudflare R2 Workers API: developers.cloudflare.com/r2/api/workers/workers-api-usage
