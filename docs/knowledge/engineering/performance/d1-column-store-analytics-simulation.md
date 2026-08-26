# D1 Column Store Simulation for Analytics Queries
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A D1 database stores time-series events (page views, purchase events, error logs) in a standard
row-oriented table. Analytical queries—`GROUP BY`, `SUM`, `COUNT`, range aggregations over
millions of rows—run in 1–5 s and frequently hit D1's per-query row-scan limits. D1 does not
support columnar storage natively, but the same write path can be restructured to simulate
column-store behaviour: narrow aggregate tables that pre-compute the most common rollups, reducing
full-table scans to indexed point reads.

## Context

SQLite (D1's engine) is row-oriented: scanning 10 M event rows to compute `SUM(revenue)` by day
reads every column even if only `ts` and `revenue` are needed. A column-store places each
column's values contiguously, reducing I/O to the relevant columns only.

D1's practical constraints:
- Max 10 GB per database (2026).
- No columnar extensions (Parquet, Arrow) are supported.
- `EXPLAIN QUERY PLAN` shows "SCAN TABLE" for unindexed aggregations—these are expensive.

The simulation approach uses **pre-aggregated rollup tables** written at event ingest time (or via
a scheduled Worker) that store only the aggregate columns needed for analytics queries. The raw
events table remains the source of truth; rollup tables are materialized views maintained in
application code.

## Schema Design

```sql
-- Raw events table (source of truth, append-only)
CREATE TABLE IF NOT EXISTS events (
  id        INTEGER PRIMARY KEY,
  ts        INTEGER NOT NULL,   -- Unix ms
  user_id   TEXT NOT NULL,
  event     TEXT NOT NULL,
  revenue   REAL DEFAULT 0,
  country   TEXT,
  source    TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);

-- Hourly rollup (column-store simulation: only the aggregated columns)
CREATE TABLE IF NOT EXISTS rollup_hourly (
  hour_bucket INTEGER NOT NULL,   -- Unix ms, truncated to hour
  country     TEXT NOT NULL,
  source      TEXT NOT NULL,
  pageviews   INTEGER DEFAULT 0,
  purchases   INTEGER DEFAULT 0,
  revenue     REAL DEFAULT 0,
  PRIMARY KEY (hour_bucket, country, source)
) WITHOUT ROWID;

-- Daily rollup
CREATE TABLE IF NOT EXISTS rollup_daily (
  day_bucket  INTEGER NOT NULL,   -- Unix ms, truncated to day
  country     TEXT NOT NULL,
  pageviews   INTEGER DEFAULT 0,
  purchases   INTEGER DEFAULT 0,
  revenue     REAL DEFAULT 0,
  PRIMARY KEY (day_bucket, country)
) WITHOUT ROWID;
```

`WITHOUT ROWID` on rollup tables eliminates the hidden rowid column and stores rows in primary-key
order, enabling efficient range scans over `(hour_bucket, country, source)` without a secondary
index.

## Rollup Maintenance at Ingest

```typescript
// src/event-ingest.ts
interface Env {
  DB: D1Database;
}

interface InboundEvent {
  userId: string;
  event: 'pageview' | 'purchase';
  revenue?: number;
  country: string;
  source: string;
}

function truncateToHour(tsMs: number): number {
  return Math.floor(tsMs / 3_600_000) * 3_600_000;
}

function truncateToDay(tsMs: number): number {
  return Math.floor(tsMs / 86_400_000) * 86_400_000;
}

export async function ingestEvent(
  db: D1Database,
  ev: InboundEvent,
  tsMs = Date.now(),
): Promise<void> {
  const hourBucket = truncateToHour(tsMs);
  const dayBucket = truncateToDay(tsMs);
  const revenue = ev.revenue ?? 0;
  const isPurchase = ev.event === 'purchase' ? 1 : 0;
  const isPageview = ev.event === 'pageview' ? 1 : 0;

  // Write raw event + update both rollups atomically
  await db.batch([
    db.prepare(
      'INSERT INTO events (ts, user_id, event, revenue, country, source) VALUES (?, ?, ?, ?, ?, ?)',
    ).bind(tsMs, ev.userId, ev.event, revenue, ev.country, ev.source),

    // Upsert hourly rollup — INSERT OR REPLACE accumulates via excluded
    db.prepare(`
      INSERT INTO rollup_hourly (hour_bucket, country, source, pageviews, purchases, revenue)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT (hour_bucket, country, source) DO UPDATE SET
        pageviews = pageviews + excluded.pageviews,
        purchases = purchases + excluded.purchases,
        revenue   = revenue   + excluded.revenue
    `).bind(hourBucket, ev.country, ev.source, isPageview, isPurchase, revenue),

    db.prepare(`
      INSERT INTO rollup_daily (day_bucket, country, pageviews, purchases, revenue)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT (day_bucket, country) DO UPDATE SET
        pageviews = pageviews + excluded.pageviews,
        purchases = purchases + excluded.purchases,
        revenue   = revenue   + excluded.revenue
    `).bind(dayBucket, ev.country, isPageview, isPurchase, revenue),
  ]);
}
```

The `db.batch()` call wraps all three statements in a single D1 transaction, keeping rollups
consistent with raw events.

## Analytical Queries Against Rollup Tables

```typescript
// src/analytics-queries.ts

// Revenue by country for the last 7 days — reads rollup_daily only
export async function revenueByCountry(
  db: D1Database,
  fromMs: number,
  toMs: number,
): Promise<Array<{ country: string; revenue: number; purchases: number }>> {
  const result = await db
    .prepare(`
      SELECT country,
             SUM(revenue)   AS revenue,
             SUM(purchases) AS purchases
      FROM   rollup_daily
      WHERE  day_bucket >= ? AND day_bucket < ?
      GROUP  BY country
      ORDER  BY revenue DESC
      LIMIT  100
    `)
    .bind(fromMs, toMs)
    .all<{ country: string; revenue: number; purchases: number }>();

  return result.results;
}

// Hourly pageview trend for a specific country — reads rollup_hourly
export async function hourlyPageviews(
  db: D1Database,
  country: string,
  fromMs: number,
  toMs: number,
): Promise<Array<{ hour: number; pageviews: number }>> {
  const result = await db
    .prepare(`
      SELECT hour_bucket AS hour,
             SUM(pageviews) AS pageviews
      FROM   rollup_hourly
      WHERE  country = ?
        AND  hour_bucket >= ?
        AND  hour_bucket < ?
      GROUP  BY hour_bucket
      ORDER  BY hour_bucket ASC
    `)
    .bind(country, fromMs, toMs)
    .all<{ hour: number; pageviews: number }>();

  return result.results;
}
```

These queries scan only the `(hour_bucket, country)` prefix of `WITHOUT ROWID` rollup tables—
equivalent to a column-store scan over the three relevant columns.

## Backfill Rollups From Raw Events

```typescript
// src/backfill.ts — run via a scheduled Worker for historical data
export async function backfillHourlyRollup(
  db: D1Database,
  fromMs: number,
  toMs: number,
): Promise<void> {
  // Aggregate raw events into rollup in a single SQL INSERT ... SELECT
  await db.exec(`
    INSERT INTO rollup_hourly (hour_bucket, country, source, pageviews, purchases, revenue)
    SELECT
      (ts / 3600000) * 3600000 AS hour_bucket,
      country,
      source,
      SUM(CASE WHEN event = 'pageview'  THEN 1 ELSE 0 END) AS pageviews,
      SUM(CASE WHEN event = 'purchase'  THEN 1 ELSE 0 END) AS purchases,
      SUM(revenue) AS revenue
    FROM events
    WHERE ts >= ${fromMs} AND ts < ${toMs}
    GROUP BY hour_bucket, country, source
    ON CONFLICT (hour_bucket, country, source) DO UPDATE SET
      pageviews = pageviews + excluded.pageviews,
      purchases = purchases + excluded.purchases,
      revenue   = revenue   + excluded.revenue
  `);
}
```

## EXPLAIN Verification

```sql
EXPLAIN QUERY PLAN
SELECT country, SUM(revenue)
FROM rollup_daily
WHERE day_bucket >= 1753920000000 AND day_bucket < 1754006400000
GROUP BY country;
-- Expected: SEARCH rollup_daily USING PRIMARY KEY (day_bucket>? AND day_bucket<?)
-- NOT: SCAN TABLE events
```

Compare with the naive raw-events query:
```sql
EXPLAIN QUERY PLAN
SELECT country, SUM(revenue)
FROM events
WHERE ts >= 1753920000000 AND ts < 1754006400000
GROUP BY country;
-- SCAN TABLE events USING INDEX idx_events_ts — still scans all rows in range
```

## Anti-patterns

- **Updating rollups after reads**: rollups must be written at ingest time (or in a scheduled
  catch-up job). Updating them in a read handler adds write latency to query paths.
- **Using rollups for exact deduplication queries**: rollups aggregate; they cannot answer
  "unique users" without a HyperLogLog approximation stored in a separate column.
- **Creating rollups without `WITHOUT ROWID`**: the hidden rowid adds 8 bytes per row and
  prevents primary-key-order storage. Use `WITHOUT ROWID` for all rollup tables.
- **Skipping the `ON CONFLICT ... DO UPDATE` clause**: without it, concurrent writes produce
  unique constraint violations. Always upsert rollup rows.
- **Partitioning rollups by too many dimensions**: each additional `GROUP BY` column multiplies
  rollup table rows. Model only the dimensions your dashboard actually queries.

## Gotchas

- D1's `db.exec()` does not support parameterised queries; interpolate safe integers only. Use
  `db.prepare().bind()` for user-supplied values.
- `WITHOUT ROWID` tables do not support `INTEGER PRIMARY KEY` autoincrement. Use composite
  primary keys that fully define the row as shown.
- SQLite's `(ts / 3600000) * 3600000` integer division truncates correctly to the epoch-millisecond
  hour boundary without `datetime()` functions, which avoids timezone complexity in D1.
- D1 batch size is limited to 100 statements per `batch()` call. For bulk ingest, chunk event
  arrays into batches of ≤33 events (3 statements each).
- Rollup tables become authoritative for analytics; do not delete them to save space without
  rebuilding from raw events.

## Verification

Run the following after deploying:

```typescript
// Confirm rollup row count vs raw events
const [rollup, raw] = await db.batch([
  db.prepare('SELECT COUNT(*) AS n FROM rollup_daily'),
  db.prepare('SELECT COUNT(*) AS n FROM events'),
]);
// rollup.results[0].n should be << raw.results[0].n
// (one rollup row per day×country combination, vs one raw row per event)
```

Query latency benchmark: `revenueByCountry()` over 30-day window should complete in <50 ms against
rollup tables vs 1–5 s against raw events for a 10 M row dataset.

## Related

- `d1-query-performance-explain-index.md`
- `d1-prepared-statement-reuse.md`
- `d1-batch-query-performance-optimization.md`
- `d1-query-optimization.md`
- `workers-subrequest-fanout-parallelism.md`

## Sources

- SQLite Docs: WITHOUT ROWID Tables — https://www.sqlite.org/withoutrowid.html
- SQLite Docs: UPSERT — https://www.sqlite.org/lang_upsert.html
- Cloudflare Docs: D1 — https://developers.cloudflare.com/d1/
- Cloudflare Docs: D1 Batch — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- "Column Stores for Wide Tables" — The Art of PostgreSQL, Chapter 14 (analogous principles)
