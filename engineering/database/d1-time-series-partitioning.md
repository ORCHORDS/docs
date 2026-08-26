# Time-Series Data Modeling in D1 with Partitioning Strategies
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You are ingesting time-ordered events into Cloudflare D1 — user activity logs, sensor
readings, audit trails, pricing snapshots, or metrics — and queries are slowing down as the
table grows past a few million rows. You need to keep recent data fast, archive old data
cost-effectively, and avoid the table bloat that makes full scans expensive in SQLite.

## Context

SQLite (and therefore D1) does not support native declarative partitioning the way PostgreSQL
does. However, several patterns simulate partition pruning:

- **Table-per-period partitioning**: separate tables per month/year, query only the relevant
  table(s).
- **Row bucketing with partial indexes**: a `bucket` column derived from the timestamp, with
  partial indexes per bucket.
- **Rolling archival to R2**: aged-out data exported as Parquet/JSON-L to R2, hot data
  stays in D1.
- **Hybrid D1 + Analytics Engine**: D1 holds relational time-series, Cloudflare Analytics
  Engine holds high-cardinality metrics.

This article covers the first three patterns in depth.

---

## Pattern 1 — Table-per-Period Partitioning

Create one table per calendar month. A routing layer in the Worker directs reads and writes
to the correct table(s).

```sql
-- Template schema (repeat per period)
-- migrations/0020_events_2026_08.sql
CREATE TABLE IF NOT EXISTS events_2026_08 (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id     TEXT NOT NULL,
  event_type  TEXT NOT NULL,
  payload     TEXT,                    -- JSON blob
  occurred_at INTEGER NOT NULL,        -- Unix epoch ms
  CHECK (occurred_at >= 1754006400000  -- 2026-08-01 00:00 UTC
     AND occurred_at <  1756684800000) -- 2026-09-01 00:00 UTC
);

CREATE INDEX IF NOT EXISTS idx_events_2026_08_user_time
  ON events_2026_08 (user_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_events_2026_08_type_time
  ON events_2026_08 (event_type, occurred_at DESC);
```

### Worker routing layer

```typescript
// src/time-series/router.ts

function tableForEpochMs(ms: number): string {
  const d = new Date(ms);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  return `events_${y}_${m}`;
}

function tablesInRange(fromMs: number, toMs: number): string[] {
  const tables: string[] = [];
  const cur = new Date(fromMs);
  cur.setUTCDate(1);
  cur.setUTCHours(0, 0, 0, 0);

  while (cur.getTime() <= toMs) {
    const y = cur.getUTCFullYear();
    const m = String(cur.getUTCMonth() + 1).padStart(2, "0");
    tables.push(`events_${y}_${m}`);
    cur.setUTCMonth(cur.getUTCMonth() + 1);
  }
  return tables;
}

export async function insertEvent(
  db: D1Database,
  userId: string,
  eventType: string,
  payload: unknown,
  occurredAt: number
): Promise<void> {
  const table = tableForEpochMs(occurredAt);
  await db
    .prepare(
      `INSERT INTO ${table} (user_id, event_type, payload, occurred_at)
       VALUES (?, ?, ?, ?)`
    )
    .bind(userId, eventType, JSON.stringify(payload), occurredAt)
    .run();
}

export async function queryRange(
  db: D1Database,
  userId: string,
  fromMs: number,
  toMs: number,
  limit = 100
): Promise<unknown[]> {
  const tables = tablesInRange(fromMs, toMs);

  // Query each relevant partition and union results
  const results = await db.batch(
    tables.map((t) =>
      db
        .prepare(
          `SELECT * FROM ${t}
           WHERE  user_id = ?
             AND  occurred_at BETWEEN ? AND ?
           ORDER  BY occurred_at DESC
           LIMIT  ?`
        )
        .bind(userId, fromMs, toMs, limit)
    )
  );

  return results
    .flatMap((r) => r.results)
    .sort((a: any, b: any) => b.occurred_at - a.occurred_at)
    .slice(0, limit);
}
```

### Auto-provisioning new monthly tables

```typescript
// src/time-series/provision.ts
// Called by a Cron Trigger on the 25th of each month
export async function provisionNextMonthTable(db: D1Database): Promise<void> {
  const now  = new Date();
  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
  const y    = next.getUTCFullYear();
  const m    = String(next.getUTCMonth() + 1).padStart(2, "0");

  // First day of month+1 for the CHECK constraint upper bound
  const monthStart = next.getTime();
  const monthEnd   = new Date(Date.UTC(y, next.getUTCMonth() + 1, 1)).getTime();

  await db.exec(`
    CREATE TABLE IF NOT EXISTS events_${y}_${m} (
      id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
      user_id     TEXT NOT NULL,
      event_type  TEXT NOT NULL,
      payload     TEXT,
      occurred_at INTEGER NOT NULL,
      CHECK (occurred_at >= ${monthStart} AND occurred_at < ${monthEnd})
    );
    CREATE INDEX IF NOT EXISTS idx_events_${y}_${m}_user_time
      ON events_${y}_${m} (user_id, occurred_at DESC);
    CREATE INDEX IF NOT EXISTS idx_events_${y}_${m}_type_time
      ON events_${y}_${m} (event_type, occurred_at DESC);
  `);

  console.log(`Provisioned events_${y}_${m}`);
}
```

---

## Pattern 2 — Row Bucketing with Partial Indexes

When table-per-period adds too much operational complexity, use a single table with a `bucket`
column and partial indexes to achieve similar pruning.

```sql
-- migrations/0021_events_bucketed.sql
CREATE TABLE IF NOT EXISTS events (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id     TEXT NOT NULL,
  event_type  TEXT NOT NULL,
  payload     TEXT,
  occurred_at INTEGER NOT NULL,
  -- Integer year-month bucket: 202608, 202609, …
  bucket      INTEGER NOT NULL
    GENERATED ALWAYS AS (
      (occurred_at / 86400000 / 30)   -- approximate 30-day buckets
    ) STORED
);

-- Partial index for recent 30 days (bucket >= current - 1)
-- SQLite does not allow dynamic expressions in partial index WHERE clauses,
-- so create one index per "active" bucket and drop aged ones.
CREATE INDEX IF NOT EXISTS idx_events_bucket_recent
  ON events (user_id, occurred_at DESC)
  WHERE bucket >= 18800;  -- replace with (today_epoch_ms / 86400000 / 30) - 1

-- Full covering index for historical queries (no WHERE filter)
CREATE INDEX IF NOT EXISTS idx_events_user_time
  ON events (user_id, occurred_at DESC);
```

Note: partial index `WHERE` expressions in SQLite must be constants, not expressions. You
must recreate the partial index as the active bucket changes (e.g., monthly via Cron Trigger).

---

## Pattern 3 — Rolling Archival to R2

Move rows older than a retention threshold from D1 to R2 as JSON-L, keeping D1 lean.

```typescript
// src/time-series/archive.ts
import type { Env } from "../types";

const RETENTION_MS = 90 * 24 * 60 * 60 * 1000; // 90 days

export async function archiveOldEvents(env: Env): Promise<void> {
  const cutoff = Date.now() - RETENTION_MS;

  // Determine which monthly tables are entirely before the cutoff
  const tables = await listEventTables(env.DB);
  const cutoffYM = epochMsToYM(cutoff);

  for (const table of tables) {
    const tableYM = tableNameToYM(table);
    if (tableYM >= cutoffYM) continue; // still within retention

    // Export all rows to R2
    const rows = await env.DB.prepare(`SELECT * FROM ${table}`).all();
    if (rows.results.length > 0) {
      const jsonl = rows.results.map((r) => JSON.stringify(r)).join("\n");
      const r2Key = `archive/${table}.jsonl`;
      await env.BACKUPS.put(r2Key, jsonl, {
        httpMetadata: { contentType: "application/x-ndjson" },
      });
    }

    // Drop the archived table from D1
    await env.DB.exec(`DROP TABLE IF EXISTS ${table}`);
    console.log(`Archived and dropped: ${table} (${rows.results.length} rows)`);
  }
}

async function listEventTables(db: D1Database): Promise<string[]> {
  const res = await db
    .prepare(`SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'events_%'`)
    .all<{ name: string }>();
  return res.results.map((r) => r.name);
}

function epochMsToYM(ms: number): number {
  const d = new Date(ms);
  return d.getUTCFullYear() * 100 + (d.getUTCMonth() + 1); // e.g. 202608
}

function tableNameToYM(name: string): number {
  // "events_2026_08" -> 202608
  const parts = name.split("_");
  return parseInt(parts[1]) * 100 + parseInt(parts[2]);
}
```

---

## Aggregate Query Across Partitions

For dashboard queries that span multiple partitions, use D1's `batch()` and merge in the
Worker rather than a slow UNION ALL across tables:

```typescript
// src/time-series/aggregate.ts
export async function dailyCounts(
  db: D1Database,
  fromMs: number,
  toMs: number,
  eventType: string
): Promise<{ date: string; count: number }[]> {
  const tables = tablesInRange(fromMs, toMs);

  const batchResults = await db.batch(
    tables.map((t) =>
      db
        .prepare(
          `SELECT date(occurred_at / 1000, 'unixepoch') AS date, COUNT(*) AS cnt
           FROM   ${t}
           WHERE  event_type = ?
             AND  occurred_at BETWEEN ? AND ?
           GROUP  BY date`
        )
        .bind(eventType, fromMs, toMs)
    )
  );

  // Merge and sum across partitions
  const map = new Map<string, number>();
  for (const batch of batchResults) {
    for (const row of batch.results as { date: string; cnt: number }[]) {
      map.set(row.date, (map.get(row.date) ?? 0) + row.cnt);
    }
  }

  return Array.from(map.entries())
    .map(([date, count]) => ({ date, count }))
    .sort((a, b) => a.date.localeCompare(b.date));
}
```

---

## Anti-patterns

- **Single `events` table with no partitioning**: A 50M-row single table in SQLite causes
  multi-second range scans even with indexes, because SQLite's query planner cannot prune
  pages that fall outside the time range. Partition early.

- **Using `TEXT` for `occurred_at`**: ISO 8601 strings sort correctly but are 10-24x larger
  than INTEGER epoch milliseconds and slower to compare. Always store timestamps as INTEGER
  Unix epoch (ms or s, be consistent).

- **Unbounded `IN (table1, table2, ...)` unions in SQL**: D1 does not support `UNION ALL`
  across dynamically named tables inside a single SQL string. Use Worker-level `batch()` and
  merge results.

- **Archiving to R2 without indexing the archive**: Archived JSON-L in R2 is write-once but
  read-never without a way to find it. Maintain a manifest table in D1 recording which
  R2 keys cover which date ranges.

- **Dropping tables without verifying the R2 write succeeded**: If R2 `put` fails silently
  (network error), then `DROP TABLE` destroys data permanently. Always confirm the R2 write
  before dropping.

---

## Gotchas

- **D1 `batch()` result ordering**: Results of a `batch()` call are returned in the same
  order as the input statements. The merge loop can rely on this.

- **SQLite page cache and large tables**: D1 manages its page cache on Cloudflare's
  infrastructure. Very large tables (> 1 GB) may see higher tail latencies during full scans
  because the cache cold-starts on each Worker invocation.

- **`date()` function timezone**: SQLite's `date()` function defaults to UTC. If your users
  are in different timezones and you need local-time bucketing, store both UTC epoch and a
  local date column, or apply the offset in the Worker.

- **Generated `bucket` column and inserts**: When using the bucketing pattern, `INSERT INTO
  events (id, user_id, ...) VALUES (...)` must NOT include `bucket` in the column list — it
  is always computed. Include it and D1 will return `SQLITE_ERROR: cannot store in generated
  column`.

---

## Verification

```sql
-- List all partition tables and their row counts
SELECT name,
       (SELECT COUNT(*) FROM sqlite_master m2
        WHERE  m2.type = 'table' AND m2.name = m.name) AS exists_flag
FROM   sqlite_master m
WHERE  type = 'table'
  AND  name LIKE 'events_%'
ORDER  BY name;

-- Row counts per partition (run for each table name from above)
SELECT 'events_2026_08' AS tbl, COUNT(*) AS cnt FROM events_2026_08;

-- Verify indexes are being used (query planner should show INDEX SCAN)
EXPLAIN QUERY PLAN
SELECT * FROM events_2026_08
WHERE  user_id = 'u123'
  AND  occurred_at > 1754006400000
ORDER  BY occurred_at DESC
LIMIT  50;
-- Expect: "USING INDEX idx_events_2026_08_user_time"
```

---

## Related

- `time-series-data-cloudflare-analytics-engine.md` — high-cardinality metrics should go here
- `d1-batch-operations-performance.md` — batching partition inserts efficiently
- `d1-backup-point-in-time-recovery.md` — archiving aged partitions to R2
- `d1-json-column-patterns.md` — modeling event payloads as JSON in D1
- `timeseries-database-patterns.md` — TimescaleDB alternative for Postgres workloads

## Sources

- SQLite indexes and query planner: https://www.sqlite.org/queryplanner.html
- Cloudflare D1 performance best practices: https://developers.cloudflare.com/d1/best-practices/query-d1/
- Cloudflare Analytics Engine for metrics: https://developers.cloudflare.com/analytics/analytics-engine/
- SQLite generated columns: https://www.sqlite.org/gencol.html
