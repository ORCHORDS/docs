# D1 Database Size Growth Monitoring with Analytics Engine

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A D1 database storing user-generated content grows continuously. The team does not track row counts or file sizes until queries begin slowing down or the Cloudflare dashboard shows the database approaching the 10 GB per-database limit (as of 2025). By that point, emergency cleanup or migration work is needed under operational pressure. Proactive time-series tracking of D1 size, row counts, and index sizes in Analytics Engine provides early warnings and enables capacity planning before the database becomes a bottleneck.

## Context

D1 does not natively push size metrics to any observability pipeline. The measurement approach uses a scheduled Worker that:
1. Queries D1's internal `sqlite_master` and `dbstat` virtual tables to read table and index sizes.
2. Queries row counts via `COUNT(*)` per table.
3. Writes all metrics to Analytics Engine.

The `dbstat` virtual table (available in SQLite and exposed in D1) returns per-page statistics that, multiplied by `page_size`, give exact byte sizes per table and index. This avoids any dependency on Cloudflare billing APIs and works with the standard D1 binding available in every Worker.

## Sampling Worker

```typescript
// src/d1-size-sampler.ts
// Scheduled: "0 * * * *" (hourly)

export interface Env {
  DB: D1Database;
  AE: AnalyticsEngineDataset;
  DATABASE_NAME: string;
}

interface TableStats {
  tableName: string;
  rowCount: number;
  dataBytes: number;
  indexBytes: number;
}

interface DbStats {
  totalBytes: number;
  pageSize: number;
  pageCount: number;
  tables: TableStats[];
}

async function collectD1Stats(db: D1Database): Promise<DbStats> {
  // Step 1: get page_size and page_count from PRAGMA
  const pragmaResult = await db.batch([
    db.prepare('PRAGMA page_size'),
    db.prepare('PRAGMA page_count'),
  ]);

  const pageSize: number = (pragmaResult[0].results[0] as { page_size: number }).page_size;
  const pageCount: number = (pragmaResult[1].results[0] as { page_count: number }).page_count;
  const totalBytes = pageSize * pageCount;

  // Step 2: get all user tables (exclude sqlite internal tables)
  const tablesResult = await db
    .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%'")
    .all<{ name: string }>();

  const tableNames = tablesResult.results.map(r => r.name);

  // Step 3: per-table row count (batched)
  const countStatements = tableNames.map(name =>
    db.prepare(`SELECT COUNT(*) AS row_count FROM "${name}"`)
  );
  const countResults = await db.batch(countStatements);

  // Step 4: per-table byte sizes via dbstat
  // dbstat returns one row per page; SUM(payload) approximates data bytes.
  // 'aggregate' mode (supported in newer SQLite) gives one row per name.
  const dbstatStatements = tableNames.map(name =>
    db.prepare(
      `SELECT SUM(payload) AS data_bytes, SUM(unused) AS unused_bytes FROM dbstat WHERE name = ?`
    ).bind(name)
  );
  const dbstatResults = await db.batch(dbstatStatements);

  const tables: TableStats[] = tableNames.map((tableName, i) => {
    const rowCount = (countResults[i].results[0] as { row_count: number }).row_count;
    const dataBytes = (dbstatResults[i].results[0] as { data_bytes: number | null }).data_bytes ?? 0;
    return { tableName, rowCount, dataBytes, indexBytes: 0 };
  });

  // Step 5: per-index sizes
  const indexResult = await db
    .prepare(
      "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    )
    .all<{ name: string; tbl_name: string }>();

  const indexDbstatStatements = indexResult.results.map(idx =>
    db.prepare(
      `SELECT '${idx.tbl_name}' AS tbl_name, SUM(payload) AS index_bytes FROM dbstat WHERE name = ?`
    ).bind(idx.name)
  );

  if (indexDbstatStatements.length > 0) {
    const indexDbstatResults = await db.batch(indexDbstatStatements);
    for (const result of indexDbstatResults) {
      const row = result.results[0] as { tbl_name: string; index_bytes: number | null } | undefined;
      if (!row) continue;
      const tableEntry = tables.find(t => t.tableName === row.tbl_name);
      if (tableEntry) tableEntry.indexBytes += row.index_bytes ?? 0;
    }
  }

  return { totalBytes, pageSize, pageCount, tables };
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const stats = await collectD1Stats(env.DB);

    // Write one data point for the overall database
    env.AE.writeDataPoint({
      blobs:   [env.DATABASE_NAME, '__total__'],
      doubles: [stats.totalBytes, stats.pageCount, stats.pageSize, 0, 0],
      indexes: [env.DATABASE_NAME],
    });

    // Write one data point per table
    for (const table of stats.tables) {
      env.AE.writeDataPoint({
        blobs:   [env.DATABASE_NAME, table.tableName],
        // double1=data_bytes, double2=index_bytes, double3=row_count
        // double4=bytes_per_row (average), double5=fill_ratio (vs 10 GB limit)
        doubles: [
          table.dataBytes,
          table.indexBytes,
          table.rowCount,
          table.rowCount > 0 ? table.dataBytes / table.rowCount : 0,
          stats.totalBytes / (10 * 1024 * 1024 * 1024),
        ],
        indexes: [`${env.DATABASE_NAME}::${table.tableName}`],
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

```toml
# wrangler.toml
name = "d1-size-sampler"
main = "src/d1-size-sampler.ts"
compatibility_date = "2025-09-01"

[triggers]
crons = ["0 * * * *"]

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "d1_size_metrics"

[vars]
DATABASE_NAME = "my-app-db"
```

## Analytics Engine Queries

```sql
-- Current total database size and fill ratio
SELECT
  blob1                              AS database,
  last_value(double1) / 1073741824   AS current_gb,
  last_value(double2)                AS page_count,
  last_value(double5) * 100          AS fill_pct
FROM d1_size_metrics
WHERE
  blob2 = '__total__'
  AND timestamp >= NOW() - INTERVAL '2' HOUR
GROUP BY database;
```

```sql
-- Per-table breakdown: data bytes, index bytes, row count
SELECT
  blob2                             AS table_name,
  last_value(double1) / 1048576     AS data_mb,
  last_value(double2) / 1048576     AS index_mb,
  last_value(double3)               AS row_count,
  last_value(double4)               AS bytes_per_row
FROM d1_size_metrics
WHERE
  blob1 = 'my-app-db'
  AND blob2 != '__total__'
  AND timestamp >= NOW() - INTERVAL '2' HOUR
GROUP BY table_name
ORDER BY data_mb DESC;
```

```sql
-- 30-day growth trend: daily total database size
SELECT
  toStartOfDay(timestamp)            AS day,
  last_value(double1) / 1073741824   AS total_gb
FROM d1_size_metrics
WHERE
  blob1 = 'my-app-db'
  AND blob2 = '__total__'
  AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY day
ORDER BY day;
```

```sql
-- Growth rate per table (bytes/day over last 7 days)
SELECT
  blob2 AS table_name,
  (last_value(double1) - first_value(double1))
    / dateDiff('day', min(timestamp), max(timestamp))     AS data_bytes_per_day,
  (last_value(double3) - first_value(double3))
    / dateDiff('day', min(timestamp), max(timestamp))     AS rows_per_day
FROM d1_size_metrics
WHERE
  blob1 = 'my-app-db'
  AND blob2 != '__total__'
  AND timestamp >= NOW() - INTERVAL '7' DAY
GROUP BY table_name
HAVING dateDiff('day', min(timestamp), max(timestamp)) >= 3
ORDER BY data_bytes_per_day DESC;
```

## Capacity Alert Worker

```typescript
// src/d1-capacity-alert.ts
// Scheduled daily: "0 7 * * *"

export interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  AE_DATASET: string;
  DATABASE_NAME: string;
  ALERT_WEBHOOK: string;
  WARN_FILL_PCT: string;  // e.g. "70"
  CRIT_FILL_PCT: string;  // e.g. "85"
  FORECAST_DAYS: string;  // e.g. "30"
}

interface SizeRow {
  current_gb: number;
  fill_pct: number;
}

interface GrowthRow {
  data_gb_per_day: number;
}

async function query<T>(env: Env, sql: string): Promise<T[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  const json = await res.json<{ data: T[] }>();
  return json.data;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const warnPct = Number(env.WARN_FILL_PCT ?? 70);
    const critPct = Number(env.CRIT_FILL_PCT ?? 85);
    const forecastDays = Number(env.FORECAST_DAYS ?? 30);
    const db = env.DATABASE_NAME;

    const [sizeRows, growthRows] = await Promise.all([
      query<SizeRow>(env, `
        SELECT last_value(double1)/1073741824 AS current_gb,
               last_value(double5)*100        AS fill_pct
        FROM ${env.AE_DATASET}
        WHERE blob1='${db}' AND blob2='__total__'
          AND timestamp >= NOW() - INTERVAL '2' HOUR
      `),
      query<GrowthRow>(env, `
        SELECT (last_value(double1)-first_value(double1))
                 / dateDiff('day',min(timestamp),max(timestamp)) / 1073741824
               AS data_gb_per_day
        FROM ${env.AE_DATASET}
        WHERE blob1='${db}' AND blob2='__total__'
          AND timestamp >= NOW() - INTERVAL '14' DAY
        HAVING dateDiff('day',min(timestamp),max(timestamp)) >= 3
      `),
    ]);

    const currentGb   = sizeRows[0]?.current_gb ?? 0;
    const fillPct     = sizeRows[0]?.fill_pct ?? 0;
    const gbPerDay    = growthRows[0]?.data_gb_per_day ?? 0;

    const remainingGb = 10 - currentGb;
    const daysToFull  = gbPerDay > 0 ? remainingGb / gbPerDay : Infinity;
    const daysTo80    = gbPerDay > 0 ? (8 - currentGb) / gbPerDay : Infinity; // 80% of 10 GB

    const messages: string[] = [];

    if (fillPct >= critPct) {
      messages.push(`CRITICAL: D1 ${db} is ${fillPct.toFixed(1)}% full (${currentGb.toFixed(2)} GB / 10 GB)`);
    } else if (fillPct >= warnPct) {
      messages.push(`WARNING: D1 ${db} is ${fillPct.toFixed(1)}% full (${currentGb.toFixed(2)} GB / 10 GB)`);
    }

    if (daysTo80 <= forecastDays && currentGb < 8) {
      messages.push(`FORECAST: D1 ${db} will reach 80% capacity in ~${daysTo80.toFixed(1)} days at current growth rate (${(gbPerDay * 1024).toFixed(1)} MB/day)`);
    }

    if (messages.length > 0) {
      ctx.waitUntil(
        fetch(env.ALERT_WEBHOOK, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: messages.join('\n') }),
        })
      );
    }
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- **Relying solely on the Cloudflare dashboard for size visibility**: The dashboard shows current total size but provides no historical trend, no per-table breakdown, and no alerting. Time-series data in Analytics Engine is required for capacity planning.
- **Running `SELECT COUNT(*) FROM large_table` on the primary request path**: Full table scans for monitoring should only run in scheduled Workers, not inline with user requests. Even with an index, `COUNT(*)` without a `WHERE` clause scans all rows.
- **Using `dbstat` without checking D1 compatibility**: The `dbstat` virtual table is available in D1 as of the 2024 compatibility date. Verify against the Cloudflare changelog if deploying on older compatibility dates.
- **Alerting on absolute byte values without accounting for page fragmentation**: SQLite (and D1) allocate storage in pages. After large deletes, `page_count * page_size` (total allocated) is larger than actual data bytes. Run `PRAGMA auto_vacuum = INCREMENTAL` and periodic `PRAGMA incremental_vacuum` to reclaim freed pages and make size metrics meaningful.

## Gotchas

- **D1 batch statement limit**: D1 batch calls are limited to 100 statements per batch. If a database has more than ~45 tables (counting both data and index stat queries), split the batch into multiple calls.
- **`dbstat` payload column semantics**: `SUM(payload)` approximates stored data bytes, not the raw page bytes. The actual on-disk footprint is `page_count * page_size`. For capacity planning, use the `page_count` PRAGMA result — it reflects the actual file size including fragmentation.
- **D1 in beta — limits change**: D1's per-database size limit (10 GB as of 2025), row size limits, and statement timeouts are subject to change. Parameterize all thresholds in `[vars]` so they can be updated without code changes.
- **Analytics Engine write cost**: At 1 data point per table per hour, a database with 20 tables produces 480 data points per day — well within limits. At 100 tables, you produce 2,400 data points per day, still manageable, but note that Analytics Engine is billed per data point on paid plans.

## Verification

```bash
# Run the sampler manually to verify data collection
wrangler dev --trigger scheduled

# Or invoke the D1 PRAGMA directly
wrangler d1 execute my-app-db --command "PRAGMA page_count; PRAGMA page_size;"

# Check for data in Analytics Engine (after first scheduled run)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob2 AS tbl, last_value(double1)/1048576 AS mb FROM d1_size_metrics WHERE blob1='\''my-app-db'\'' AND timestamp >= NOW() - INTERVAL '\''2'\'' HOUR GROUP BY tbl ORDER BY mb DESC LIMIT 20"}' \
  | jq '.data'
```

## Related

- `d1-query-latency-histogram-analytics-engine.md` — D1 query latency monitoring
- `d1-explain-query-plan-slow-query-automation.md` — slow query detection with EXPLAIN
- `analytics-engine-write-limits-and-backpressure.md` — Analytics Engine write limits
- `durable-objects-storage-growth-forecasting-analytics-engine.md` — Durable Objects storage forecasting

## Sources

- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
- SQLite dbstat virtual table: https://www.sqlite.org/dbstat.html
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- D1 compatibility dates: https://developers.cloudflare.com/d1/platform/compatibility-dates/
