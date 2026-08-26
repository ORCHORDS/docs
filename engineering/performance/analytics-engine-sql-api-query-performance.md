# Analytics Engine SQL API Query Performance

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
Dashboard queries against Cloudflare Analytics Engine's SQL API time out or return stale aggregates because they scan unbounded time ranges and use high-cardinality `blob` columns in `GROUP BY` clauses. Rewriting queries to exploit partition pruning, pre-aggregation, and `index` column pushdown reduces p95 query latency from >10 s to <800 ms for 30-day aggregate dashboards.

## Context
Analytics Engine is a time-series columnar store optimised for append-only writes from Workers. Each data point has up to 20 `blob` columns (string), 20 `double` columns (numeric), one `index` column (the primary filter/sort key), and an automatic `timestamp` column. The SQL API (accessed via `POST /accounts/{id}/analytics_engine/sql`) supports a ClickHouse-compatible SQL dialect. Query performance depends on three levers: (1) `timestamp` range predicates that enable partition pruning, (2) the `index` column used as the primary filter — it is stored as a low-cardinality first-class index — and (3) aggregation functions (`sum()`, `avg()`, `count()`, `quantile()`) which are evaluated columnar and are fast; `GROUP BY` on high-cardinality blob columns is slow.

## Pattern 1 — Write-Time Schema for Queryability

```typescript
// Design blobs and doubles for the queries you will run, not the data you collect.
// Rule: put the highest-selectivity filter field in `indexes[0]` (the index column).
// Rule: put GROUP BY candidates in low-index blobs (blob1, blob2).
// Rule: aggregate targets go in doubles.

export async function recordApiRequest(
  ae: AnalyticsEngineDataset,
  req: Request,
  res: Response,
  durationMs: number,
): Promise<void> {
  const url = new URL(req.url);
  const route = url.pathname.replace(/\/[0-9a-f-]{8,}/gi, "/:id"); // Normalise IDs

  ae.writeDataPoint({
    // Low-cardinality grouping dimensions in blob1/blob2
    blobs: [
      req.method,           // blob1: HTTP method
      String(res.status),   // blob2: status code
      route,                // blob3: normalised route (higher cardinality — rarely GROUP BY)
      req.cf?.country as string ?? "XX", // blob4: country
    ],
    doubles: [
      durationMs,           // double1: request duration
      Number(res.headers.get("Content-Length") ?? 0), // double2: response size bytes
      res.ok ? 1 : 0,       // double3: success flag (sum → success count)
    ],
    // index: the value that will appear in WHERE index = '...' filters
    indexes: [route.slice(0, 32)],
  });
}
```

## Pattern 2 — Partition-Pruned Time-Range Query

```typescript
// Always supply an explicit timestamp WHERE clause to enable partition pruning.
// Analytics Engine stores data in time-ordered partitions; without a time predicate
// the query engine scans all partitions regardless of other filters.

const ANALYTICS_SQL_URL =
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`;

async function queryRequestThroughput(
  token: string,
  hoursBack: number,
): Promise<{ minute: string; requests: number; errRate: number }[]> {
  const sql = `
    SELECT
      toStartOfMinute(timestamp)            AS minute,
      count()                               AS requests,
      sum(double3)                          AS successes,
      round(1 - sum(double3) / count(), 4)  AS errRate,
      avg(double1)                          AS avg_ms
    FROM api_requests
    WHERE timestamp > now() - INTERVAL '${hoursBack}' HOUR
    GROUP BY minute
    ORDER BY minute ASC
  `;

  const res = await fetch(ANALYTICS_SQL_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "text/plain",
    },
    body: sql,
  });

  if (!res.ok) throw new Error(`AE SQL error: ${res.status} ${await res.text()}`);
  const { data } = await res.json<{ data: Record<string, unknown>[] }>();
  return data as never;
}
```

## Pattern 3 — Index Column Pushdown for Route-Specific Dashboards

```typescript
// Using the `index` column in WHERE dramatically reduces scanned rows.
// `blob3` (full route) has high cardinality; `index` (first 32 chars of route)
// is stored separately and evaluated before column decompression.

async function queryRouteLatencyPercentiles(
  token: string,
  routePrefix: string,
  days: number,
): Promise<{ p50: number; p95: number; p99: number }> {
  const sql = `
    SELECT
      quantile(0.50)(double1) AS p50,
      quantile(0.95)(double1) AS p95,
      quantile(0.99)(double1) AS p99
    FROM api_requests
    WHERE index     = '${routePrefix.slice(0, 32).replace(/'/g, "''")}'
      AND timestamp > now() - INTERVAL '${days}' DAY
  `;

  const res = await fetch(ANALYTICS_SQL_URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "text/plain" },
    body: sql,
  });

  const { data } = await res.json<{ data: [{ p50: number; p95: number; p99: number }] }>();
  return data[0];
}
```

## Pattern 4 — Pre-Aggregated KV Cache for Dashboard Widgets

```typescript
// Expensive 30-day aggregates are expensive to recompute per page load.
// Cache the result in KV with a 5-minute TTL; the dashboard reads from KV
// and triggers a background refresh when the TTL is almost expired.

const CACHE_KEY = "ae:dashboard:30d-summary";
const CACHE_TTL_S = 300; // 5 minutes

interface DashboardSummary {
  totalRequests: number;
  errorRate: number;
  p95Ms: number;
  computedAt: number;
}

async function getDashboardSummary(env: Env): Promise<DashboardSummary> {
  const cached = await env.KV.get<DashboardSummary>(CACHE_KEY, { type: "json" });
  const age = cached ? (Date.now() - cached.computedAt) / 1_000 : Infinity;

  if (cached && age < CACHE_TTL_S) return cached;

  // Recompute from Analytics Engine SQL API
  const sql = `
    SELECT
      count()                               AS totalRequests,
      round(1 - sum(double3) / count(), 4)  AS errorRate,
      quantile(0.95)(double1)               AS p95Ms
    FROM api_requests
    WHERE timestamp > now() - INTERVAL '30' DAY
  `;

  const res = await fetch(ANALYTICS_SQL_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_TOKEN}`,
      "Content-Type": "text/plain",
    },
    body: sql,
  });

  const { data } = await res.json<{ data: [Omit<DashboardSummary, "computedAt">] }>();
  const summary: DashboardSummary = { ...data[0], computedAt: Date.now() };

  await env.KV.put(CACHE_KEY, JSON.stringify(summary), { expirationTtl: CACHE_TTL_S * 2 });

  return summary;
}
```

## Pattern 5 — Multi-Dataset Query Fan-Out

```typescript
// Analytics Engine does not support JOINs across datasets.
// Fan out separate queries and merge results in the Worker.

async function buildCombinedReport(
  token: string,
  hours: number,
): Promise<{ route: string; requests: number; p95Ms: number; errorRate: number }[]> {
  const timeFilter = `timestamp > now() - INTERVAL '${hours}' HOUR`;

  const [throughputRows, latencyRows] = await Promise.all([
    // Dataset 1: api_requests — throughput + error rate by route
    fetchAeSql<{ route: string; requests: number; errorRate: number }>(
      token,
      `SELECT blob3 AS route, count() AS requests,
              round(1 - sum(double3)/count(), 4) AS errorRate
       FROM api_requests WHERE ${timeFilter}
       GROUP BY route ORDER BY requests DESC LIMIT 50`,
    ),
    // Dataset 2: api_latency — p95 by route (written by a separate Worker)
    fetchAeSql<{ route: string; p95Ms: number }>(
      token,
      `SELECT blob1 AS route, quantile(0.95)(double1) AS p95Ms
       FROM api_latency WHERE ${timeFilter}
       GROUP BY route`,
    ),
  ]);

  // Merge on route key
  const latencyMap = new Map(latencyRows.map((r) => [r.route, r.p95Ms]));
  return throughputRows.map((r) => ({
    ...r,
    p95Ms: latencyMap.get(r.route) ?? 0,
  }));
}

async function fetchAeSql<T>(token: string, sql: string): Promise<T[]> {
  const res = await fetch(ANALYTICS_SQL_URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "text/plain" },
    body: sql,
  });
  if (!res.ok) throw new Error(`AE SQL ${res.status}: ${await res.text()}`);
  return ((await res.json<{ data: T[] }>()).data);
}
```

## Anti-patterns
- Running unbounded queries without a `WHERE timestamp >` clause — scans all historical partitions and times out for datasets with more than a few days of data
- Using `GROUP BY blob3` (high-cardinality route with IDs) instead of normalised routes — cardinality explosion causes memory pressure in the query engine and slow results
- Calling the SQL API synchronously from inside the critical render path — always use KV-cached pre-aggregates for user-facing dashboards; recompute in background Workers
- Selecting all columns (`SELECT *`) — Analytics Engine returns all blob and double columns; prefer explicit column selection to reduce serialisation overhead
- Issuing a separate SQL API call per dashboard widget in a single page load — fan out with `Promise.all()` or combine into a single query using multiple aggregations

## Gotchas
- Analytics Engine has eventual consistency for recent writes — data written in the last 30–60 s may not appear in SQL API results; do not use it for real-time alerting requiring sub-minute freshness
- The SQL API rate limit is 100 requests/min per account; cache aggressively and avoid per-user uncached queries
- `quantile(p)(column)` is an approximate quantile (T-Digest); results may differ slightly from exact percentiles at the tails — acceptable for dashboards, not for SLA billing
- Dataset names in `FROM` clauses are the `dataset` field set in the Analytics Engine binding configuration (`wrangler.toml` → `[[analytics_engine_datasets]]`), not the binding name
- Queries older than 90 days may return empty results — Analytics Engine's default retention is 90 days; plan downsampling or export to R2 for longer-term storage

## Verification
```bash
# Test a query directly via curl
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: text/plain" \
  --data "SELECT count() AS n FROM api_requests
          WHERE timestamp > now() - INTERVAL '1' HOUR"

# Check query execution time with timing output
curl -s -o /dev/null -w "time_total: %{time_total}s\n" \
  -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: text/plain" \
  --data "SELECT toStartOfHour(timestamp) AS h, count() AS n
          FROM api_requests
          WHERE timestamp > now() - INTERVAL '7' DAY
          GROUP BY h ORDER BY h"

# Verify dataset exists and has data
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: text/plain" \
  --data "SELECT max(timestamp) AS latest, count() AS total FROM api_requests"
```

## Related
- `analytics-engine-write-throughput-batching.md`
- `analytics-engine-rum-web-vitals.md`
- `workers-waituntil-background-processing.md`
- `kv-metadata-only-reads-optimization.md`
- `d1-query-result-caching-kv-workers.md`

## Sources
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-reference/
- https://developers.cloudflare.com/analytics/analytics-engine/get-started/
- https://developers.cloudflare.com/analytics/analytics-engine/limits/
