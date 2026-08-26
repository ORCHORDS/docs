# Time Series Data Storage in D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers application collects per-metric measurements (latency, error rate, request count, temperature readings) at high frequency and needs to query rolling averages, detect gaps in the series, and downsample raw data for charting. Storing every raw measurement forever fills D1's per-database size limit and makes aggregation queries increasingly slow without careful schema and index design.

## Context

D1 is SQLite. SQLite handles time series well at moderate data volumes when composite indexes on `(metric_name, ts)` are present and queries always filter on both columns. Partitioning in the traditional sense (separate files per time bucket) does not exist in SQLite, but a `time_bucket` column emulating partition pruning achieves a similar effect. A scheduled Worker cron performs TTL-based cleanup and downsampling aggregation, ensuring the raw table stays bounded. Recursive CTEs fill gaps in sparse time series without a dedicated numbers table.

## Solution

```typescript
// src/db/timeseries.ts
import type { D1Database } from '@cloudflare/workers-types';

// ----- Schema (run via migration) ------------------------------------------

export const TIMESERIES_SCHEMA_SQL = `
  -- Raw measurements table.
  -- time_bucket: floor(ts / bucket_seconds) — emulates partition pruning.
  CREATE TABLE IF NOT EXISTS metrics_raw (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name  TEXT    NOT NULL,
    ts           INTEGER NOT NULL,   -- Unix epoch seconds
    time_bucket  INTEGER NOT NULL,   -- floor(ts / 3600) — hourly bucket
    value        REAL    NOT NULL,
    tags         TEXT                -- JSON {region, host, ...}
  );

  -- The most important index: covers the most common query pattern.
  CREATE INDEX IF NOT EXISTS idx_metrics_name_ts
    ON metrics_raw(metric_name, ts);

  -- Bucket index: used for TTL cleanup and downsampling.
  CREATE INDEX IF NOT EXISTS idx_metrics_bucket
    ON metrics_raw(time_bucket);

  -- Downsampled hourly rollup table (1 row per metric per hour).
  CREATE TABLE IF NOT EXISTS metrics_hourly (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name  TEXT    NOT NULL,
    bucket_ts    INTEGER NOT NULL,   -- start of hour (Unix epoch)
    count        INTEGER NOT NULL,
    sum          REAL    NOT NULL,
    min          REAL    NOT NULL,
    max          REAL    NOT NULL,
    p50          REAL,               -- approximated
    UNIQUE (metric_name, bucket_ts)
  );

  CREATE INDEX IF NOT EXISTS idx_metrics_hourly_name_bucket
    ON metrics_hourly(metric_name, bucket_ts);
`;

// ----- Types ----------------------------------------------------------------

export interface RawPoint {
  metricName: string;
  ts: number;    // Unix epoch seconds
  value: number;
  tags?: Record<string, string>;
}

export interface HourlyBucket {
  bucketTs: number;
  count: number;
  sum: number;
  avg: number;
  min: number;
  max: number;
}

export interface RollingAvgPoint {
  ts: number;
  rollingAvg: number;
}

// ----- Write path -----------------------------------------------------------

export async function insertMetrics(
  db: D1Database,
  points: RawPoint[]
): Promise<void> {
  if (points.length === 0) return;

  const BUCKET_SECONDS = 3600; // hourly bucket

  const statements = points.map((p) =>
    db
      .prepare(
        `INSERT INTO metrics_raw (metric_name, ts, time_bucket, value, tags)
         VALUES (?, ?, ?, ?, ?)`
      )
      .bind(
        p.metricName,
        p.ts,
        Math.floor(p.ts / BUCKET_SECONDS),
        p.value,
        p.tags ? JSON.stringify(p.tags) : null
      )
  );

  // Batch insert: up to 100 statements per D1 batch.
  for (let i = 0; i < statements.length; i += 100) {
    await db.batch(statements.slice(i, i + 100));
  }
}

// ----- Downsampling aggregation (called from cron) -------------------------

export async function downsampleHour(
  db: D1Database,
  metricName: string,
  bucketTs: number // start of the hour
): Promise<void> {
  const BUCKET_SECONDS = 3600;
  const bucketId = Math.floor(bucketTs / BUCKET_SECONDS);

  const row = await db
    .prepare(
      `SELECT
         COUNT(*)   AS count,
         SUM(value) AS sum,
         MIN(value) AS min,
         MAX(value) AS max,
         -- SQLite has no built-in percentile; use median approximation.
         value AS p50
       FROM (
         SELECT value,
                ROW_NUMBER() OVER (ORDER BY value) AS rn,
                COUNT(*) OVER ()                   AS total
         FROM metrics_raw
         WHERE metric_name = ?
           AND time_bucket = ?
       )
       WHERE rn = (total + 1) / 2
      `
    )
    .bind(metricName, bucketId)
    .first<{ count: number; sum: number; min: number; max: number; p50: number | null }>();

  if (!row || row.count === 0) return;

  // Upsert into hourly rollup.
  await db
    .prepare(
      `INSERT INTO metrics_hourly (metric_name, bucket_ts, count, sum, min, max, p50)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (metric_name, bucket_ts) DO UPDATE SET
         count = excluded.count,
         sum   = excluded.sum,
         min   = excluded.min,
         max   = excluded.max,
         p50   = excluded.p50`
    )
    .bind(metricName, bucketTs, row.count, row.sum, row.min, row.max, row.p50 ?? null)
    .run();
}

// ----- TTL cleanup ----------------------------------------------------------

export async function cleanupRawMetrics(
  db: D1Database,
  retentionHours: number = 48
): Promise<number> {
  const BUCKET_SECONDS = 3600;
  const cutoffBucket = Math.floor(Date.now() / 1000 / BUCKET_SECONDS) - retentionHours;

  let total = 0;
  while (true) {
    const result = await db
      .prepare(
        `DELETE FROM metrics_raw
         WHERE id IN (
           SELECT id FROM metrics_raw
           WHERE time_bucket < ?
           LIMIT 200
         )`
      )
      .bind(cutoffBucket)
      .run();
    const n = result.meta.changes ?? 0;
    total += n;
    if (n < 200) break;
  }

  console.log(`[timeseries] cleaned up ${total} raw points older than ${retentionHours}h.`);
  return total;
}

// ----- Gap-filling query with recursive CTE --------------------------------

export async function queryWithGapFill(
  db: D1Database,
  metricName: string,
  fromTs: number,
  toTs: number,
  stepSeconds: number = 3600
): Promise<Array<{ ts: number; avg: number | null }>> {
  // Generate a dense time series using a recursive CTE,
  // then LEFT JOIN actual data to fill gaps with NULL.
  const rows = await db
    .prepare(
      `WITH RECURSIVE
       spine(ts) AS (
         VALUES (?)
         UNION ALL
         SELECT ts + ? FROM spine WHERE ts + ? <= ?
       ),
       agg AS (
         SELECT
           (ts / ?) * ? AS bucket,
           AVG(value)   AS avg
         FROM metrics_raw
         WHERE metric_name = ?
           AND ts BETWEEN ? AND ?
         GROUP BY bucket
       )
       SELECT
         spine.ts,
         agg.avg
       FROM spine
       LEFT JOIN agg ON agg.bucket = spine.ts
       ORDER BY spine.ts`
    )
    .bind(
      fromTs,
      stepSeconds, stepSeconds, toTs,   // spine params
      stepSeconds, stepSeconds,          // agg bucket params
      metricName, fromTs, toTs           // agg filter params
    )
    .all<{ ts: number; avg: number | null }>();

  return rows.results;
}

// ----- Windowed rolling average --------------------------------------------

export async function rollingAverage(
  db: D1Database,
  metricName: string,
  fromTs: number,
  toTs: number,
  windowSeconds: number = 3600
): Promise<RollingAvgPoint[]> {
  // Compute a rolling average using a self-join window.
  // Each point's average includes all raw values within
  // the preceding windowSeconds.
  const rows = await db
    .prepare(
      `SELECT
         r.ts,
         AVG(w.value) AS rolling_avg
       FROM metrics_raw r
       JOIN metrics_raw w
         ON w.metric_name = r.metric_name
        AND w.ts BETWEEN r.ts - ? AND r.ts
       WHERE r.metric_name = ?
         AND r.ts BETWEEN ? AND ?
       GROUP BY r.ts
       ORDER BY r.ts`
    )
    .bind(windowSeconds, metricName, fromTs, toTs)
    .all<{ ts: number; rolling_avg: number }>();

  return rows.results.map((r) => ({ ts: r.ts, rollingAvg: r.rolling_avg }));
}

// ----- Worker entry point with cron ----------------------------------------

// src/index.ts
export interface Env {
  DB: D1Database;
  RAW_RETENTION_HOURS?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/metrics') {
      const body = await request.json<{ points: RawPoint[] }>();
      await insertMetrics(env.DB, body.points);
      return new Response(null, { status: 204 });
    }

    if (url.pathname === '/metrics/rollup') {
      const name = url.searchParams.get('name') ?? '';
      const from = parseInt(url.searchParams.get('from') ?? '0', 10);
      const to = parseInt(url.searchParams.get('to') ?? '0', 10);
      const step = parseInt(url.searchParams.get('step') ?? '3600', 10);
      const series = await queryWithGapFill(env.DB, name, from, to, step);
      return Response.json({ series });
    }

    return new Response('Not Found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const retention = parseInt(env.RAW_RETENTION_HOURS ?? '48', 10);
    // 1. Downsample the previous complete hour.
    const prevHourStart =
      Math.floor(Date.now() / 1000 / 3600) * 3600 - 3600;

    const metrics = await env.DB
      .prepare(`SELECT DISTINCT metric_name FROM metrics_raw WHERE time_bucket = ?`)
      .bind(Math.floor(prevHourStart / 3600))
      .all<{ metric_name: string }>();

    for (const { metric_name } of metrics.results) {
      await downsampleHour(env.DB, metric_name, prevHourStart);
    }

    // 2. Clean up raw data older than retention window.
    await cleanupRawMetrics(env.DB, retention);
  },
};
```

## Implementation Details

**`time_bucket` column** — storing `floor(ts / 3600)` as a plain integer column allows the cleanup cron and downsampling queries to filter using the `idx_metrics_bucket` index without a full-table scan. Without this column, range deletions must scan every row to evaluate `ts < cutoff`.

**Composite index `(metric_name, ts)`** — the most selective filters in time series queries are `metric_name = ?` and `ts BETWEEN ? AND ?`. A composite index in this order allows SQLite to seek directly to the metric's rows and range-scan only the requested time window.

**Recursive CTE spine** — generates a dense sequence of timestamps from `fromTs` to `toTs` at `stepSeconds` intervals. The `LEFT JOIN` to aggregated data fills gaps with `NULL` rather than omitting points. Frontend chart libraries interpret `NULL` as a missing value and can render it as a gap or interpolate it.

**Rolling average self-join** — joins the raw table to itself on `ts BETWEEN r.ts - windowSeconds AND r.ts`. This is an O(n²) operation for large windows; restrict `fromTs`/`toTs` to reasonable ranges and prefer the hourly rollup table for wide windows.

**Downsampled rollup** — `metrics_hourly` stores pre-computed aggregates per hour per metric. Charts covering weeks or months should query `metrics_hourly`, not `metrics_raw`. The `UPSERT` (`ON CONFLICT DO UPDATE`) makes the cron idempotent.

**Batch-size-limited cleanup** — deletes 200 rows per D1 statement, looping until fewer than 200 are deleted. This keeps individual D1 calls well within the 10 MB response-size limit and avoids timing out the `scheduled` handler.

## Anti-patterns

- **No index on `(metric_name, ts)`** — without this, every aggregation query performs a full table scan.
- **Storing raw data indefinitely** — D1 has a per-database size limit; unbounded raw storage will exhaust it.
- **Using `datetime()` strings instead of Unix epoch integers** — string comparison is slower than integer comparison; epoch integers sort and range-scan correctly.
- **Wide rolling average windows over the raw table** — computing a 7-day rolling average from raw second-resolution data using a self-join is prohibitively expensive. Query the rollup table instead.
- **Recursive CTE without a depth bound** — for `stepSeconds = 1` and a week-long range, the spine generates 604,800 rows. Add a `WHERE ts + step <= toTs` termination condition (already included above) and enforce maximum range widths at the application layer.

## Gotchas

- SQLite's `ROW_NUMBER()` window function requires SQLite 3.25+. D1 runs a recent SQLite version that supports it, but verify if using other environments.
- The recursive CTE spine generates rows in memory. For very fine-grained steps over long ranges, it may exhaust D1's per-query memory budget. Cap the range or increase the step.
- `AVG()` returns `NULL` for empty groups. The `LEFT JOIN` preserves spine rows with no matching data as `avg: null`; handle `null` in the client.
- D1's `scheduled()` handler has a 30-second CPU limit. For databases with many distinct metric names, partition the downsampling cron across multiple scheduled events.
- The self-join rolling average assumes timestamps are evenly distributed. Sparse data produces correct averages but may be misleading; consider gap-fill before averaging.

## Verification

```typescript
async function verifyTimeSeries(db: D1Database) {
  const now = Math.floor(Date.now() / 1000);

  // Insert 10 raw points over the last hour.
  const points: RawPoint[] = Array.from({ length: 10 }, (_, i) => ({
    metricName: 'test.latency',
    ts: now - i * 360,
    value: Math.random() * 100,
  }));
  await insertMetrics(db, points);

  // Query gap-filled series.
  const series = await queryWithGapFill(db, 'test.latency', now - 3600, now, 360);
  console.assert(series.length > 0, 'gap-fill returns points');
  console.assert(
    series.every((p) => typeof p.ts === 'number'),
    'all spine points have ts'
  );

  // Rolling average.
  const rolling = await rollingAverage(db, 'test.latency', now - 3600, now, 720);
  console.assert(rolling.length > 0, 'rolling average returns points');

  // Cleanup.
  const deleted = await cleanupRawMetrics(db, 0); // 0h retention = delete all
  console.assert(deleted === 10, `deleted ${deleted} rows`);
}
```

## Related

- [workers-d1-schema-versioning](workers-d1-schema-versioning.md)
- [workers-d1-soft-delete-pattern](workers-d1-soft-delete-pattern.md)

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/windowfunctions.html
- https://www.sqlite.org/lang_with.html
- https://www.sqlite.org/partialindex.html
