# D1 Time Series Data Patterns — Window Functions, Downsampling, and Rollup Tables

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to store event-rate metrics, IoT readings, API latency samples, or user activity events in D1 and serve fast dashboard queries ("last 7 days p95", "hourly request counts"). Naive one-row-per-event schemas collapse under read load and breach D1's 10 GB database limit long before your retention window closes.

## Context

D1 runs SQLite 3.45 under the hood, which supports window functions (since SQLite 3.25), `strftime()` for time bucketing, and partial indexes. Pair these with a two-table pattern — raw events + pre-aggregated rollup — to keep dashboard latency under 50 ms while staying within Workers' 50 ms CPU budget per subrequest.

## 1 — Schema Design for Time Series

```typescript
// migrations/0001_timeseries.sql
const SCHEMA = `
CREATE TABLE IF NOT EXISTS events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT    NOT NULL,
  ts        INTEGER NOT NULL,  -- Unix epoch seconds
  value     REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_entity_ts
  ON events (entity_id, ts DESC);

CREATE TABLE IF NOT EXISTS rollups_hourly (
  entity_id TEXT    NOT NULL,
  bucket    INTEGER NOT NULL,  -- floored to hour: ts - (ts % 3600)
  min_val   REAL    NOT NULL,
  max_val   REAL    NOT NULL,
  avg_val   REAL    NOT NULL,
  count     INTEGER NOT NULL,
  PRIMARY KEY (entity_id, bucket)
);
`;

export async function applySchema(db: D1Database) {
  await db.exec(SCHEMA);
}
```

## 2 — Bucketed Inserts with Automatic Rollup Upsert

```typescript
interface Env { DB: D1Database; }

export async function recordEvent(
  db: D1Database,
  entityId: string,
  value: number,
  nowSec = Math.floor(Date.now() / 1000),
): Promise<void> {
  const bucket = nowSec - (nowSec % 3600);

  await db.batch([
    db.prepare(
      `INSERT INTO events (entity_id, ts, value) VALUES (?, ?, ?)`
    ).bind(entityId, nowSec, value),

    db.prepare(`
      INSERT INTO rollups_hourly (entity_id, bucket, min_val, max_val, avg_val, count)
      VALUES (?, ?, ?, ?, ?, 1)
      ON CONFLICT (entity_id, bucket) DO UPDATE SET
        min_val = MIN(min_val, excluded.min_val),
        max_val = MAX(max_val, excluded.max_val),
        avg_val = (avg_val * count + excluded.avg_val) / (count + 1),
        count   = count + 1
    `).bind(entityId, bucket, value, value, value),
  ]);
}
```

## 3 — Window Functions for Moving Average

```typescript
export async function movingAverage(
  db: D1Database,
  entityId: string,
  windowHours = 6,
): Promise<{ bucket: number; avg_val: number; moving_avg: number }[]> {
  const result = await db.prepare(`
    SELECT
      bucket,
      avg_val,
      AVG(avg_val) OVER (
        PARTITION BY entity_id
        ORDER BY bucket
        ROWS BETWEEN ? PRECEDING AND CURRENT ROW
      ) AS moving_avg
    FROM rollups_hourly
    WHERE entity_id = ?
      AND bucket >= strftime('%s', 'now', '-7 days')
    ORDER BY bucket
  `).bind(windowHours - 1, entityId).all<{
    bucket: number;
    avg_val: number;
    moving_avg: number;
  }>();

  return result.results;
}
```

## 4 — Downsampling Raw Events to Daily Buckets via Cron

```typescript
// src/cron.ts — runs via Workers Cron Trigger every hour
export async function downsampleToDailyRollup(db: D1Database): Promise<void> {
  const cutoff = Math.floor(Date.now() / 1000) - 3600 * 25; // older than 25h

  await db.prepare(`
    INSERT INTO rollups_daily (entity_id, day_bucket, min_val, max_val, avg_val, count)
    SELECT
      entity_id,
      bucket - (bucket % 86400) AS day_bucket,
      MIN(min_val),
      MAX(max_val),
      SUM(avg_val * count) / SUM(count),
      SUM(count)
    FROM rollups_hourly
    WHERE bucket < ?
    GROUP BY entity_id, day_bucket
    ON CONFLICT (entity_id, day_bucket) DO UPDATE SET
      min_val = MIN(min_val, excluded.min_val),
      max_val = MAX(max_val, excluded.max_val),
      avg_val = (avg_val * count + excluded.avg_val * excluded.count)
                / (count + excluded.count),
      count   = count + excluded.count
  `).bind(cutoff).run();

  // Prune raw events older than 48 hours
  await db.prepare(`
    DELETE FROM events WHERE ts < ?
  `).bind(cutoff - 3600).run();
}
```

## 5 — Fast Dashboard Query with Percentile Approximation

```typescript
// D1/SQLite lacks built-in percentile; approximate with ordered window
export async function percentile(
  db: D1Database,
  entityId: string,
  pct: number,   // 0.95 for p95
  sinceHours = 24,
): Promise<number | null> {
  const since = Math.floor(Date.now() / 1000) - sinceHours * 3600;

  const { results } = await db.prepare(`
    WITH ordered AS (
      SELECT value,
             ROW_NUMBER() OVER (ORDER BY value) AS rn,
             COUNT(*) OVER ()                   AS total
      FROM events
      WHERE entity_id = ? AND ts >= ?
    )
    SELECT value FROM ordered
    WHERE rn = CAST(CEIL(? * total) AS INTEGER)
    LIMIT 1
  `).bind(entityId, since, pct).all<{ value: number }>();

  return results[0]?.value ?? null;
}
```

## 6 — Pagination Over Time Ranges (Keyset)

```typescript
export async function pageEvents(
  db: D1Database,
  entityId: string,
  afterTs?: number,
  limit = 100,
): Promise<{ id: number; ts: number; value: number }[]> {
  const query = afterTs
    ? db.prepare(
        `SELECT id, ts, value FROM events
         WHERE entity_id = ? AND ts < ?
         ORDER BY ts DESC LIMIT ?`
      ).bind(entityId, afterTs, limit)
    : db.prepare(
        `SELECT id, ts, value FROM events
         WHERE entity_id = ?
         ORDER BY ts DESC LIMIT ?`
      ).bind(entityId, limit);

  const { results } = await query.all<{ id: number; ts: number; value: number }>();
  return results;
}
```

## Anti-patterns

- **One row per millisecond without bucketing** — exceeds D1's row throughput and grows the database past 10 GB quickly. Always bucket writes at insert time.
- **Missing composite index on `(entity_id, ts DESC)`** — full-table scans for every "last N days" query. The index is the single most important performance lever.
- **`DELETE FROM events WHERE ts < ?` without an index on `ts`** — SQLite must scan the whole table. Index `ts` separately or add it to the composite index.
- **Computing percentiles via `ORDER BY + LIMIT OFFSET`** — offset pagination is O(n). Use the window-function keyset approach above.

## Gotchas

- Window functions require SQLite 3.25+; D1 ships 3.45 so all window functions are available.
- `strftime('%s', 'now')` in D1 returns a string, not an integer — cast with `CAST(strftime('%s','now') AS INTEGER)` in expressions.
- D1 Read Replicas are eventually consistent — dashboard queries on replicas may lag writes by up to a few seconds. Point live ingestion at the primary.
- D1's `db.batch()` executes statements in a single round-trip but is not atomic by default; wrap in `BEGIN`/`COMMIT` via `db.prepare('BEGIN')` when rollup consistency matters.
- Each D1 database is capped at 10 GB. Implement a retention policy (daily prune job) and size alerts via Analytics Engine.

## Verification

```typescript
// Smoke-test: insert 3 events, verify rollup count
const db = env.DB;
await recordEvent(db, 'test-entity', 42.0, 1700000000);
await recordEvent(db, 'test-entity', 44.0, 1700000060);
await recordEvent(db, 'test-entity', 46.0, 1700000120);

const row = await db.prepare(
  `SELECT count FROM rollups_hourly WHERE entity_id = ? AND bucket = ?`
).bind('test-entity', 1700000000 - (1700000000 % 3600)).first<{ count: number }>();

console.assert(row?.count === 3, 'Rollup count mismatch');
```

## Related

- `d1-cursor-based-pagination-large-datasets.md`
- `d1-global-read-replicas.md`
- `d1-time-travel.md`
- `cloudflare-workers-analytics-engine-custom-metrics.md`
- `workers-cron-triggers.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/windowfunctions.html
- https://developers.cloudflare.com/d1/reference/database-commands/
- https://developers.cloudflare.com/d1/observability/read-replication/
