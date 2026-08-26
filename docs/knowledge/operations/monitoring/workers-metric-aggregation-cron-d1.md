# Metric Aggregation from Analytics Engine into D1 via Cron Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Analytics Engine retains raw data points for a limited window (30 days by default). You need longer-term metric history — hourly and daily rollups stored in D1 — to power dashboards, SLA reports, and trend calculations without re-querying billions of raw events.

## Context

Analytics Engine (AE) exposes a SQL-over-HTTP API that supports `GROUP BY` aggregations. A cron-triggered Worker can query AE hourly, compute rollups, upsert them into D1 summary tables, and enforce a retention policy (keep daily rows for one year, purge hourly rows after 30 days). A separate API endpoint Worker exposes pre-aggregated metrics for dashboards.

## Solution

### 1. D1 schema

```sql
-- migrations/0001_metric_rollups.sql
CREATE TABLE IF NOT EXISTS metric_hourly (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  metric_name TEXT    NOT NULL,
  dimension   TEXT    NOT NULL DEFAULT '',
  hour_bucket TEXT    NOT NULL,  -- ISO-8601 truncated to hour: 2026-08-24T13:00:00Z
  count       INTEGER NOT NULL DEFAULT 0,
  sum         REAL    NOT NULL DEFAULT 0,
  min         REAL    NOT NULL DEFAULT 0,
  max         REAL    NOT NULL DEFAULT 0,
  p50         REAL    NOT NULL DEFAULT 0,
  p99         REAL    NOT NULL DEFAULT 0,
  recorded_at TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE(metric_name, dimension, hour_bucket)
);

CREATE TABLE IF NOT EXISTS metric_daily (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  metric_name TEXT    NOT NULL,
  dimension   TEXT    NOT NULL DEFAULT '',
  day_bucket  TEXT    NOT NULL,  -- ISO-8601 date: 2026-08-24
  count       INTEGER NOT NULL DEFAULT 0,
  sum         REAL    NOT NULL DEFAULT 0,
  min         REAL    NOT NULL DEFAULT 0,
  max         REAL    NOT NULL DEFAULT 0,
  p50         REAL    NOT NULL DEFAULT 0,
  p99         REAL    NOT NULL DEFAULT 0,
  recorded_at TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE(metric_name, dimension, day_bucket)
);

CREATE INDEX IF NOT EXISTS idx_hourly_name_bucket ON metric_hourly(metric_name, hour_bucket);
CREATE INDEX IF NOT EXISTS idx_daily_name_bucket  ON metric_daily(metric_name, day_bucket);
```

### 2. Analytics Engine SQL aggregation query

```typescript
// src/lib/ae-query.ts
export interface AERow {
  metric_name: string;
  dimension: string;
  bucket: string;
  count: number;
  sum: number;
  min: number;
  max: number;
}

export async function queryAEHourlyRollup(
  accountId: string,
  apiToken: string,
  dataset: string,
  targetHour: Date
): Promise<AERow[]> {
  // AE SQL uses toStartOfHour(), toStartOfDay() helpers
  const hourStr = targetHour.toISOString().slice(0, 13) + ':00:00Z';
  const sql = `
    SELECT
      index1                          AS metric_name,
      index2                          AS dimension,
      toStartOfHour(timestamp)        AS bucket,
      COUNT()                         AS count,
      SUM(double1)                    AS sum,
      MIN(double1)                    AS min,
      MAX(double1)                    AS max
    FROM ${dataset}
    WHERE
      timestamp >= '${hourStr}'
      AND timestamp <  dateAdd('hour', 1, '${hourStr}')
    GROUP BY metric_name, dimension, bucket
    ORDER BY metric_name, dimension, bucket
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`AE query failed ${res.status}: ${text}`);
  }

  const json = (await res.json()) as { data: AERow[] };
  return json.data;
}
```

### 3. Cron Worker — hourly and daily rollup

```typescript
// src/workers/metric-aggregation.ts
import { queryAEHourlyRollup, AERow } from '../lib/ae-query';

interface Env {
  DB: D1Database;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  AE_DATASET: string;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const now = new Date(event.scheduledTime);

    // Hourly rollup: aggregate the previous complete hour
    const prevHour = new Date(now);
    prevHour.setUTCMinutes(0, 0, 0);
    prevHour.setUTCHours(prevHour.getUTCHours() - 1);
    await runHourlyRollup(env, prevHour);

    // Daily rollup at top of each hour — aggregate yesterday if it's 01:00 UTC
    if (now.getUTCHours() === 1) {
      const yesterday = new Date(now);
      yesterday.setUTCDate(yesterday.getUTCDate() - 1);
      await runDailyRollup(env, yesterday);
    }

    // Retention: purge hourly rows older than 30 days
    await env.DB.prepare(
      `DELETE FROM metric_hourly WHERE hour_bucket < datetime('now', '-30 days')`
    ).run();

    // Retention: purge daily rows older than 1 year
    await env.DB.prepare(
      `DELETE FROM metric_daily WHERE day_bucket < date('now', '-365 days')`
    ).run();
  },
};

async function runHourlyRollup(env: Env, targetHour: Date) {
  const rows = await queryAEHourlyRollup(
    env.CF_ACCOUNT_ID,
    env.CF_API_TOKEN,
    env.AE_DATASET,
    targetHour
  );

  if (rows.length === 0) return;

  const stmt = env.DB.prepare(`
    INSERT INTO metric_hourly (metric_name, dimension, hour_bucket, count, sum, min, max)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(metric_name, dimension, hour_bucket)
    DO UPDATE SET
      count = excluded.count,
      sum   = excluded.sum,
      min   = excluded.min,
      max   = excluded.max,
      recorded_at = datetime('now')
  `);

  const batch = rows.map((r) =>
    stmt.bind(r.metric_name, r.dimension, r.bucket, r.count, r.sum, r.min, r.max)
  );
  await env.DB.batch(batch);
}

async function runDailyRollup(env: Env, targetDay: Date) {
  const dayStr = targetDay.toISOString().slice(0, 10);
  // Roll up from hourly table — avoids re-querying AE for past days
  await env.DB.prepare(`
    INSERT INTO metric_daily (metric_name, dimension, day_bucket, count, sum, min, max)
    SELECT
      metric_name,
      dimension,
      ? AS day_bucket,
      SUM(count),
      SUM(sum),
      MIN(min),
      MAX(max)
    FROM metric_hourly
    WHERE hour_bucket >= ? AND hour_bucket < date(?, '+1 day')
    GROUP BY metric_name, dimension
    ON CONFLICT(metric_name, dimension, day_bucket)
    DO UPDATE SET
      count = excluded.count,
      sum   = excluded.sum,
      min   = excluded.min,
      max   = excluded.max,
      recorded_at = datetime('now')
  `).bind(dayStr, dayStr, dayStr).run();
}
```

### 4. Metric query API endpoint

```typescript
// src/workers/metric-api.ts
import { Hono } from 'hono';

interface Env {
  DB: D1Database;
}

const app = new Hono<{ Bindings: Env }>();

// GET /metrics/:name?dimension=&from=&to=&resolution=hourly|daily
app.get('/metrics/:name', async (c) => {
  const name = c.req.param('name');
  const dimension = c.req.query('dimension') ?? '';
  const from = c.req.query('from') ?? new Date(Date.now() - 86_400_000).toISOString();
  const to = c.req.query('to') ?? new Date().toISOString();
  const resolution = c.req.query('resolution') ?? 'hourly';

  const table = resolution === 'daily' ? 'metric_daily' : 'metric_hourly';
  const bucketCol = resolution === 'daily' ? 'day_bucket' : 'hour_bucket';

  const rows = await c.env.DB.prepare(`
    SELECT ${bucketCol} AS bucket, count, sum, min, max,
           CASE WHEN count > 0 THEN sum / count ELSE 0 END AS avg
    FROM ${table}
    WHERE metric_name = ?
      AND dimension   = ?
      AND ${bucketCol} >= ?
      AND ${bucketCol} <= ?
    ORDER BY ${bucketCol} ASC
  `).bind(name, dimension, from, to).all();

  // Trend: compare last period avg to previous period avg
  const values = rows.results.map((r: any) => r.avg as number);
  const mid = Math.floor(values.length / 2);
  const recentAvg = avg(values.slice(mid));
  const priorAvg = avg(values.slice(0, mid));
  const trendPct = priorAvg !== 0 ? ((recentAvg - priorAvg) / priorAvg) * 100 : 0;

  return c.json({
    metric: name,
    dimension,
    resolution,
    from,
    to,
    rows: rows.results,
    trend: { recent_avg: recentAvg, prior_avg: priorAvg, change_pct: trendPct },
  });
});

function avg(arr: number[]): number {
  if (arr.length === 0) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

export default app;
```

### 5. wrangler.toml cron configuration

```toml
# wrangler.toml
[triggers]
crons = ["0 * * * *"]  # top of every hour

[[d1_databases]]
binding  = "DB"
database_name = "metrics-db"
database_id   = "<your-d1-id>"

[vars]
AE_DATASET = "request_metrics"
```

## Implementation Details

- **Idempotency**: `ON CONFLICT ... DO UPDATE` ensures re-running a rollup for the same hour/day overwrites with fresh data rather than inserting duplicates. Safe to re-run on failure.
- **Batching D1 writes**: `env.DB.batch()` sends all upserts in a single HTTP round-trip, staying within the D1 batch limit of 100 statements. For >100 rows, chunk the batch.
- **AE query window alignment**: Always align the query window to complete hours to avoid partial data. The Worker queries the previous complete hour, not the current one.
- **Retention policy execution**: Run `DELETE` statements in the same cron invocation after the rollup to avoid a separate scheduled Worker.
- **p50/p99 approximation**: AE does not expose native percentile functions. Compute approximate percentiles client-side from the raw data if needed, or use AE's `quantileTDigest` if available in your account tier.

## Anti-patterns

- **Querying AE directly from dashboards**: AE SQL has rate limits and scan costs. Always serve dashboard queries from D1 rollup tables.
- **Rolling up incomplete hours**: Querying the current hour in progress gives partial data. Always roll up `now - 1 hour`.
- **Unbounded D1 growth**: Without the retention DELETE, D1 rows accumulate indefinitely and degrade query performance. Enforce retention in every cron run.
- **Storing raw AE data in D1**: D1 is not designed for high-cardinality time-series inserts. Only store pre-aggregated rollups.

## Gotchas

- AE SQL returns column names in lowercase regardless of your query aliasing. Always access result fields with lowercase keys.
- D1 `datetime()` and `date()` functions return strings, not timestamps. Compare them using string lexicographic ordering, which is safe for ISO-8601 format.
- The AE REST API endpoint URL includes your Cloudflare account ID. Store it in a secret, not a plain var.
- `event.scheduledTime` is a Unix timestamp in milliseconds. Use `new Date(event.scheduledTime)` to convert.

## Verification

1. Run the cron manually via Wrangler: `wrangler dev --test-scheduled`.
2. Query D1: `wrangler d1 execute metrics-db --command "SELECT * FROM metric_hourly ORDER BY recorded_at DESC LIMIT 10;"`.
3. Hit the API endpoint: `curl https://your-worker.workers.dev/metrics/request_duration?resolution=hourly&from=2026-08-24T00:00:00Z`.
4. Confirm trend calculation returns a non-zero `change_pct` when data spans two periods.

## Related

- `workers-structured-logging-analytics-engine` — writing raw data points to AE
- `workers-cost-per-request-tracking` — per-request cost metrics stored in AE
- `workers-error-budget-tracking-d1` — SLO error budget computed from D1 rollups
- `workers-uptime-monitor-cron-kv` — uptime metric written to AE for rollup

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/d1/reference/d1-client-api/#batch-statements
- https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
