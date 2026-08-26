# Time-Series Analytics in Cloudflare D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to store event metrics (page views, API latency samples, sensor readings) in D1 and query them as time-series: hourly buckets, rolling averages, and downsampled historical data — all without an external time-series database. D1's SQLite engine has enough window function and `strftime` support to handle these patterns at moderate scale (tens of millions of rows).

---

## Context

D1 stores time values as `TEXT` in ISO-8601 format (`2026-08-24T15:42:00Z`) because SQLite has no native datetime type. SQLite's `strftime` function truncates timestamps to any granularity, enabling GROUP BY bucketing. Window functions (`AVG() OVER (...)`) landed in SQLite 3.25 and are available in D1. Old high-resolution rows accumulate fast; a scheduled Cron Worker aggregates them to daily summaries and deletes the originals to keep the table size manageable. All queries use D1's `prepare().bind().all()` pattern for safe parameterisation.

---

## Section 1 — Schema and wrangler.toml

```toml
# wrangler.toml
name = "analytics-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "analytics"
database_id = "<your-d1-database-id>"

[triggers]
crons = ["0 3 * * *"]   # run downsampling daily at 03:00 UTC
```

```sql
-- migrations/0001_create_metrics.sql
CREATE TABLE IF NOT EXISTS metrics (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT    NOT NULL,          -- e.g. 'page_view', 'api_latency_ms'
  value       REAL    NOT NULL,
  tags        TEXT    DEFAULT '{}',      -- JSON blob for dimensions
  recorded_at TEXT    NOT NULL           -- ISO-8601, e.g. '2026-08-24T15:42:00Z'
);

CREATE INDEX IF NOT EXISTS idx_metrics_name_recorded
  ON metrics (name, recorded_at);

CREATE TABLE IF NOT EXISTS metrics_daily (
  date        TEXT NOT NULL,             -- 'YYYY-MM-DD'
  name        TEXT NOT NULL,
  count       INTEGER NOT NULL,
  sum         REAL    NOT NULL,
  min         REAL    NOT NULL,
  max         REAL    NOT NULL,
  PRIMARY KEY (date, name)
);
```

---

## Section 2 — Worker: ingest and query

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
}

// Record a single metric data point
async function ingest(
  db: D1Database,
  name: string,
  value: number,
  tags: Record<string, string> = {}
): Promise<void> {
  const recordedAt = new Date().toISOString();
  await db
    .prepare(
      "INSERT INTO metrics (name, value, tags, recorded_at) VALUES (?, ?, ?, ?)"
    )
    .bind(name, value, JSON.stringify(tags), recordedAt)
    .run();
}

// Hourly bucket query: count and avg per hour for the last N hours
async function hourlyBuckets(
  db: D1Database,
  name: string,
  hours = 24
): Promise<{ bucket: string; count: number; avg: number }[]> {
  const since = new Date(Date.now() - hours * 3600_000).toISOString();
  const { results } = await db
    .prepare(
      `SELECT
         strftime('%Y-%m-%dT%H:00', recorded_at) AS bucket,
         COUNT(*)                                AS count,
         AVG(value)                             AS avg
       FROM metrics
       WHERE name = ? AND recorded_at >= ?
       GROUP BY bucket
       ORDER BY bucket ASC`
    )
    .bind(name, since)
    .all<{ bucket: string; count: number; avg: number }>();
  return results;
}

// Rolling 7-day average using a window CTE
async function rolling7DayAvg(
  db: D1Database,
  name: string
): Promise<{ day: string; daily_avg: number; rolling_avg: number }[]> {
  const { results } = await db
    .prepare(
      `WITH daily AS (
         SELECT
           date(recorded_at)  AS day,
           AVG(value)         AS daily_avg
         FROM metrics
         WHERE name = ?
         GROUP BY day
       )
       SELECT
         day,
         daily_avg,
         AVG(daily_avg) OVER (
           ORDER BY day
           ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
         ) AS rolling_avg
       FROM daily
       ORDER BY day ASC`
    )
    .bind(name)
    .all<{ day: string; daily_avg: number; rolling_avg: number }>();
  return results;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/ingest") {
      const { name, value, tags } = await request.json<{
        name: string;
        value: number;
        tags?: Record<string, string>;
      }>();
      await ingest(env.DB, name, value, tags);
      return new Response("ok", { status: 201 });
    }

    if (url.pathname === "/hourly") {
      const name = url.searchParams.get("name") ?? "page_view";
      const hours = Number(url.searchParams.get("hours") ?? "24");
      const data = await hourlyBuckets(env.DB, name, hours);
      return Response.json(data);
    }

    if (url.pathname === "/rolling") {
      const name = url.searchParams.get("name") ?? "page_view";
      const data = await rolling7DayAvg(env.DB, name);
      return Response.json(data);
    }

    return new Response("Not found", { status: 404 });
  },

  // Cron trigger: downsample yesterday's hourly rows to daily summary
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const yesterday = new Date();
    yesterday.setUTCDate(yesterday.getUTCDate() - 1);
    const day = yesterday.toISOString().slice(0, 10); // 'YYYY-MM-DD'

    // Aggregate hourly rows into metrics_daily
    await env.DB
      .prepare(
        `INSERT OR REPLACE INTO metrics_daily (date, name, count, sum, min, max)
         SELECT
           date(recorded_at) AS date,
           name,
           COUNT(*)          AS count,
           SUM(value)        AS sum,
           MIN(value)        AS min,
           MAX(value)        AS max
         FROM metrics
         WHERE date(recorded_at) = ?
         GROUP BY name`
      )
      .bind(day)
      .run();

    // Delete raw rows older than 7 days to cap table size
    const cutoff = new Date();
    cutoff.setUTCDate(cutoff.getUTCDate() - 7);
    await env.DB
      .prepare("DELETE FROM metrics WHERE recorded_at < ?")
      .bind(cutoff.toISOString())
      .run();
  },
};
```

---

## Section 3 — Apply migration via Wrangler

```bash
npx wrangler d1 execute analytics \
  --file migrations/0001_create_metrics.sql \
  --remote
```

---

## Anti-patterns

- **Storing timestamps as Unix integers** — `strftime` works on text or numeric epochs, but ISO-8601 text sorts lexicographically without conversion, making range queries faster and human-readable.
- **Querying the full table without an index** — A missing index on `(name, recorded_at)` causes full-table scans; always add a composite index covering the two most-used filter columns.
- **Running the rolling average in application code** — Pulling all daily rows to JS and averaging them there wastes bandwidth and CPU; the SQLite window function does it in a single pass on the database side.
- **Skipping the downsampling step** — At 1 000 events/second a single metrics table grows by ~86 million rows/day; without periodic aggregation D1's 10 GB per-database limit is hit in days.

---

## Gotchas

- D1 does not support `CURRENT_TIMESTAMP` with timezone; always generate ISO-8601 in JavaScript with `new Date().toISOString()` and store UTC.
- `INSERT OR REPLACE` on `metrics_daily` requires the `PRIMARY KEY (date, name)` constraint to be present; without it you get duplicates on re-runs.
- D1 has a 10 000 row limit per single `SELECT` result; add `LIMIT` and pagination for large historical queries.
- The Cron Worker's `scheduled` handler has a 30-second CPU time limit; if downsampling is slow, batch by metric name or shard by date range.
- `wrangler d1 execute --remote` bills against your D1 row-write quota; run migrations once, not in CI on every deploy.

---

## Verification

```bash
# Ingest test data
curl -X POST https://analytics-worker.example.workers.dev/ingest \
  -H 'Content-Type: application/json' \
  -d '{"name":"page_view","value":1,"tags":{"path":"/home"}}'

# Query hourly buckets (last 24 h)
curl 'https://analytics-worker.example.workers.dev/hourly?name=page_view&hours=24'

# Query 7-day rolling average
curl 'https://analytics-worker.example.workers.dev/rolling?name=page_view'

# Inspect D1 directly
npx wrangler d1 execute analytics \
  --command "SELECT strftime('%Y-%m-%dT%H:00', recorded_at) AS h, COUNT(*) FROM metrics GROUP BY h ORDER BY h DESC LIMIT 10;" \
  --remote
```

---

## Related

- `cloudflare-pages-incremental-static-regen.md`
- `workers-geo-routing-cf-request.md`

---

## Sources

- Cloudflare D1 Docs — https://developers.cloudflare.com/d1/
- SQLite strftime reference — https://www.sqlite.org/lang_datefunc.html
- SQLite window functions — https://www.sqlite.org/windowfunctions.html
