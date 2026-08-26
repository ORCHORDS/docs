# Building a Custom Metrics Dashboard with Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need real-time observability into your Workers' business metrics — request counts, error rates, latency percentiles, or custom domain events — without shipping data to a third-party SaaS. You want to query this data from Grafana or a custom dashboard UI.

## Context

Cloudflare Analytics Engine (AE) is a time-series write store built into the Workers runtime. Each Worker can write structured data points (up to 25 blobs/doubles per point) with sub-millisecond overhead. Data is queryable via the Analytics Engine SQL API — a Cloudflare REST endpoint that accepts ClickHouse-compatible SQL. This makes it a lightweight alternative to InfluxDB or Prometheus remote-write for Cloudflare-native stacks.

Prerequisites:
- Analytics Engine dataset bound to your Worker (`wrangler.toml` `[[analytics_engine_datasets]]`)
- Cloudflare API token with `Account Analytics: Read` permission
- A separate "dashboard Worker" that proxies SQL queries (keeps the token server-side)

---

## Writing Data Points from a Worker

```typescript
// wrangler.toml (excerpt)
// [[analytics_engine_datasets]]
// binding = "ANALYTICS"
// dataset = "workers_metrics"

export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

interface RequestMetric {
  route: string;
  statusCode: number;
  durationMs: number;
  region: string;
}

function writeMetric(env: Env, metric: RequestMetric): void {
  env.ANALYTICS.writeDataPoint({
    // Up to 1 index (high-cardinality key for filtering)
    indexes: [metric.route],
    // Up to 20 blobs (string labels)
    blobs: [
      metric.route,
      metric.region,
      String(metric.statusCode),
    ],
    // Up to 20 doubles (numeric values)
    doubles: [
      metric.durationMs,
      metric.statusCode >= 500 ? 1 : 0, // error flag
      1, // request count
    ],
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);

    let response: Response;
    try {
      response = await handleRequest(request, env);
    } catch (err) {
      response = new Response("Internal Server Error", { status: 500 });
    }

    // writeDataPoint is non-blocking; use ctx.waitUntil so it doesn't
    // delay the response but also isn't dropped if the Worker exits early.
    ctx.waitUntil(
      Promise.resolve().then(() =>
        writeMetric(env, {
          route: url.pathname,
          statusCode: response.status,
          durationMs: Date.now() - start,
          region: request.cf?.colo ?? "unknown",
        })
      )
    );

    return response;
  },
};

async function handleRequest(_req: Request, _env: Env): Promise<Response> {
  return new Response("OK");
}
```

---

## Querying via the Analytics Engine SQL API

The SQL API lives at `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`.

```typescript
// dashboard-worker/src/index.ts
// This Worker is the backend for your Grafana JSON datasource or custom UI.
// It keeps the Cloudflare API token server-side.

export interface Env {
  CF_ACCOUNT_ID: string;   // set via wrangler secret
  CF_API_TOKEN: string;    // Account Analytics: Read
  DASHBOARD_SECRET: string; // shared secret for callers
}

const AE_SQL_ENDPOINT = (accountId: string) =>
  `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`;

async function queryAnalyticsEngine(
  env: Env,
  sql: string
): Promise<Record<string, unknown>[]> {
  const allRows: Record<string, unknown>[] = [];
  let cursor: string | undefined;

  // Paginate: AE returns up to 10 000 rows per page.
  do {
    const body: Record<string, unknown> = { query: sql, limit: 10000 };
    if (cursor) body.cursor = cursor;

    const res = await fetch(AE_SQL_ENDPOINT(env.CF_ACCOUNT_ID), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`AE SQL error ${res.status}: ${text}`);
    }

    const json = (await res.json()) as {
      data: Record<string, unknown>[];
      meta: { cursor?: string };
    };

    allRows.push(...json.data);
    cursor = json.meta?.cursor;
  } while (cursor);

  return allRows;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Simple bearer-token auth for the dashboard caller.
    const auth = request.headers.get("Authorization") ?? "";
    if (auth !== `Bearer ${env.DASHBOARD_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    const url = new URL(request.url);
    const from = url.searchParams.get("from") ?? "now() - INTERVAL '1' HOUR";
    const to = url.searchParams.get("to") ?? "now()";
    const route = url.searchParams.get("route") ?? "%";

    // blob1 = route, double1 = durationMs, double2 = errorFlag, double3 = count
    const sql = `
      SELECT
        toStartOfInterval(timestamp, INTERVAL '1' MINUTE) AS minute,
        blob1                                             AS route,
        count()                                           AS requests,
        sum(double3)                                      AS total,
        avg(double1)                                      AS avg_duration_ms,
        sum(double2)                                      AS errors
      FROM workers_metrics
      WHERE timestamp >= ${from}
        AND timestamp <  ${to}
        AND blob1 LIKE '${route}'
      GROUP BY minute, route
      ORDER BY minute ASC
    `;

    const rows = await queryAnalyticsEngine(env, sql);
    return Response.json({ rows });
  },
};
```

---

## Grafana JSON Datasource Integration

Install the **Marcusolini JSON** or **Infinity** Grafana plugin and point it at your dashboard Worker URL. In the panel query, set:

- **URL**: `https://dashboard.example.com/metrics?from=...&to=...`
- **Headers**: `Authorization: Bearer <DASHBOARD_SECRET>`
- **JSONata path**: `rows` → map `minute` to time, `avg_duration_ms` to value.

For the Infinity plugin, use the `UQL` mode:

```
parse-json
| scope "rows"
| project-fields minute, avg_duration_ms, errors, requests
```

---

## Paginating Large Result Sets

The AE SQL API returns a `meta.cursor` field when more pages are available. The `queryAnalyticsEngine` function above handles this automatically via a `do/while` loop. Key points:

- Maximum 10 000 rows per page; pass `limit: 10000` explicitly.
- The cursor is opaque — pass it back verbatim.
- For very large datasets, consider narrowing the time window in SQL rather than relying on pagination, since AE bills per query byte scanned.

---

## Anti-patterns

- **Writing data points synchronously inside the critical path without `ctx.waitUntil`** — `writeDataPoint` is non-blocking, but if the Worker terminates before the micro-task flushes, the point may be dropped.
- **Storing the API token in the dashboard Worker's `vars`** — use `wrangler secret put CF_API_TOKEN` so it is encrypted at rest.
- **Using `index` for low-cardinality fields** — the index column is for high-cardinality keys (user IDs, request IDs). Use blobs for enum-like labels.
- **Querying AE directly from the browser** — exposes your API token. Always proxy through a Worker.

## Gotchas

- AE data has a ~1-minute ingestion delay; dashboards should not expect sub-second freshness.
- The SQL dialect is a subset of ClickHouse SQL. `JOIN`, window functions, and subqueries are not supported as of 2026-08.
- Dataset names are global per account, not per Worker. Naming convention: `<service>_<metric_type>` (e.g., `api_requests`).
- `writeDataPoint` silently drops the write if the binding is misconfigured; add a canary alert on zero-row query results.

## Verification

```bash
# Confirm data is arriving (replace with your account ID and token)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT count() FROM workers_metrics WHERE timestamp > now() - INTERVAL 5 MINUTE"}'
# Expect: {"data":[{"count()":N}], ...} with N > 0 after sending a few requests.
```

## Related

- `workers-d1-sqlite-edge-queries.md`
- `workers-cron-distributed-lock-durable-objects.md`
- `r2-presigned-url-upload-workers.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
