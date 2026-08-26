# D1 Query Latency Histogram with Analytics Engine

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

D1 queries that average 10 ms look healthy in aggregate dashboards while individual slow queries at p99 exceed 500 ms, causing user-visible hangs on write-heavy paths. You need a per-query-label latency histogram retained for days without exporting raw logs to an external service.

## Context

Cloudflare D1 exposes no built-in per-query latency telemetry beyond the query's `meta.duration` field returned in the result object. This duration (in milliseconds, floating-point) must be captured at the application layer and written to Analytics Engine immediately after each query. Bucketing queries by table and operation type lets you identify which workloads are responsible for tail latency spikes without blowing Analytics Engine cardinality limits.

## 1. D1 Query Wrapper with Latency Capture

Wrap `db.prepare().bind().all()` / `.run()` / `.first()` in a helper that writes one data point per query execution.

```typescript
// src/d1-instrumented.ts
export interface Env {
  DB: D1Database;
  D1_LATENCY: AnalyticsEngineDataset;
}

type D1Op = "select" | "insert" | "update" | "delete" | "other";

function classifyOp(sql: string): D1Op {
  const first = sql.trimStart().slice(0, 6).toLowerCase();
  if (first.startsWith("select")) return "select";
  if (first.startsWith("insert")) return "insert";
  if (first.startsWith("update")) return "update";
  if (first.startsWith("delete")) return "delete";
  return "other";
}

export async function d1Query<T = unknown>(
  env: Env,
  table: string,
  sql: string,
  bindings: unknown[] = []
): Promise<D1Result<T>> {
  const start = performance.now();
  const op = classifyOp(sql);
  let status: "ok" | "error" = "ok";

  try {
    const stmt = env.DB.prepare(sql);
    const result: D1Result<T> = await stmt.bind(...bindings).all<T>();

    // D1 returns its own measured duration in meta.duration (ms)
    const reportedMs = result.meta.duration ?? (performance.now() - start);

    env.D1_LATENCY.writeDataPoint({
      blobs: [table, op, status],
      doubles: [reportedMs, result.results.length, result.meta.rows_read ?? 0],
      indexes: [table],
    });

    return result;
  } catch (err) {
    status = "error";
    const elapsedMs = performance.now() - start;
    env.D1_LATENCY.writeDataPoint({
      blobs: [table, op, status],
      doubles: [elapsedMs, 0, 0],
      indexes: [table],
    });
    throw err;
  }
}

export async function d1Run(
  env: Env,
  table: string,
  sql: string,
  bindings: unknown[] = []
): Promise<D1Result> {
  const start = performance.now();
  const op = classifyOp(sql);
  let status: "ok" | "error" = "ok";

  try {
    const stmt = env.DB.prepare(sql);
    const result = await stmt.bind(...bindings).run();
    const reportedMs = result.meta.duration ?? (performance.now() - start);
    env.D1_LATENCY.writeDataPoint({
      blobs: [table, op, status],
      doubles: [reportedMs, result.meta.changes ?? 0, result.meta.rows_written ?? 0],
      indexes: [table],
    });
    return result;
  } catch (err) {
    status = "error";
    env.D1_LATENCY.writeDataPoint({
      blobs: [table, op, status],
      doubles: [performance.now() - start, 0, 0],
      indexes: [table],
    });
    throw err;
  }
}
```

## 2. wrangler.toml Binding

```toml
[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "<DATABASE_ID>"

[[analytics_engine_datasets]]
binding = "D1_LATENCY"
dataset = "d1_query_latency"
```

## 3. Usage in Request Handler

```typescript
// src/index.ts
import { d1Query, d1Run, type Env } from "./d1-instrumented";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/users" && request.method === "GET") {
      const { results } = await d1Query<{ id: number; name: string }>(
        env,
        "users",
        "SELECT id, name FROM users WHERE active = ? LIMIT 100",
        [1]
      );
      return Response.json(results);
    }

    if (url.pathname === "/users" && request.method === "POST") {
      const body = await request.json<{ name: string; email: string }>();
      await d1Run(
        env,
        "users",
        "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
        [body.name, body.email, Date.now()]
      );
      return Response.json({ ok: true }, { status: 201 });
    }

    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## 4. Percentile Query via SQL API

Query the Analytics Engine SQL API from a dashboard cron Worker or an external script.

```typescript
// src/latency-report.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export interface LatencyRow {
  table_name: string;
  op: string;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  total_queries: number;
  error_count: number;
}

export async function fetchD1LatencyPercentiles(
  intervalHours = 1
): Promise<LatencyRow[]> {
  const sql = `
    SELECT
      blob1  AS table_name,
      blob2  AS op,
      quantileWeighted(0.50)(double1, 1) AS p50_ms,
      quantileWeighted(0.95)(double1, 1) AS p95_ms,
      quantileWeighted(0.99)(double1, 1) AS p99_ms,
      count() AS total_queries,
      countIf(blob3 = 'error') AS error_count
    FROM d1_query_latency
    WHERE timestamp > now() - INTERVAL '${intervalHours}' HOUR
    GROUP BY table_name, op
    ORDER BY p99_ms DESC
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!resp.ok) {
    throw new Error(`Analytics Engine SQL API error: ${resp.status}`);
  }

  const json = (await resp.json()) as { data: LatencyRow[] };
  return json.data ?? [];
}
```

## 5. SLO Alert on p99 Breach

```typescript
// src/latency-alert.ts
import { fetchD1LatencyPercentiles } from "./latency-report";

// per-table, per-op SLO budget in milliseconds
const SLO_MS: Record<string, number> = {
  "users:select": 50,
  "users:insert": 100,
  "sessions:select": 30,
  "sessions:insert": 80,
  "events:insert": 200,
};

export async function alertD1LatencySlo(
  webhookUrl: string
): Promise<void> {
  const rows = await fetchD1LatencyPercentiles(1);
  const breaches: string[] = [];

  for (const row of rows) {
    const key = `${row.table_name}:${row.op}`;
    const slo = SLO_MS[key];
    if (slo !== undefined && row.p99_ms > slo) {
      breaches.push(
        `\`${key}\` p99=${row.p99_ms.toFixed(1)}ms > SLO=${slo}ms (${row.total_queries} queries)`
      );
    }
  }

  if (breaches.length === 0) return;

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `D1 query latency SLO breach:\n${breaches.join("\n")}`,
    }),
  });
}
```

## 6. Latency Trend Query for Grafana / Dashboard

```sql
SELECT
  toStartOfInterval(timestamp, INTERVAL '5' MINUTE) AS ts,
  blob1  AS table_name,
  blob2  AS op,
  quantileWeighted(0.50)(double1, 1) AS p50_ms,
  quantileWeighted(0.99)(double1, 1) AS p99_ms,
  count() AS queries
FROM d1_query_latency
WHERE
  timestamp > now() - INTERVAL '6' HOUR
  AND blob3 = 'ok'
GROUP BY ts, table_name, op
ORDER BY ts ASC
```

## Anti-patterns

- **Using `Date.now()` deltas instead of `meta.duration`**: `Date.now()` includes Worker scheduling overhead and I/O waits outside D1 itself; prefer `result.meta.duration` which D1 measures internally.
- **Writing raw SQL strings as blob values**: full SQL text creates unbounded cardinality; use the table name and operation type labels instead.
- **Tracking only successful queries**: errors also consume D1 row budget and request quota; always write the data point in a `finally` or catch block.
- **Omitting `rows_read` tracking**: a fast query that reads 50 000 rows will degrade under load; `double3` gives early warning before latency climbs.
- **Single global SLO threshold**: read latency and write latency have different baselines; define separate budgets per `table:op` pair.

## Gotchas

- D1's `meta.duration` is measured server-side and excludes round-trip network time from the Worker to D1's SQLite backend; network variance is captured by the `performance.now()` delta.
- Analytics Engine write calls are non-blocking and fire-and-forget; a burst of writes during a D1 error storm does not back-pressure the Worker.
- `meta.duration` may be `undefined` for transactions or batch calls; always fall back to the local `performance.now()` delta.
- D1 is in a single region per database; Workers in remote PoPs see additional cross-region latency that inflates p99 measurements.
- The `indexes` field in `writeDataPoint` accepts only one value; use `blob1` (table name) as the index for efficient per-table filtering in the SQL API.

## Verification

1. Deploy the Worker and send 200 mixed SELECT and INSERT requests via `wrangler dev` or a load test.
2. After 2 minutes, call the SQL API with the percentile query and confirm rows appear for each `(table, op)` pair.
3. Artificially add `await scheduler.wait(200)` before one query type to simulate a slow query; confirm p99 climbs in the next query window.
4. Remove the sleep, lower an SLO threshold to `1` ms, run the alert Worker manually, and confirm the webhook fires.
5. Restore thresholds and validate no false positives over a 30-minute steady-state window.

## Related

- `distributed-tracing-workers-d1-durable-objects-otel.md`
- `distributed-tracing-workers-d1-requests.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `sli-slo-error-budget-d1-tracking.md`
- `d1-explain-query-plan-slow-query-automation.md`

## Sources

- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
