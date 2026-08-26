# Analytics Engine Multi-Tenant Usage Metering Dashboard

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You run a SaaS product on Cloudflare Workers where multiple tenants share the same Worker scripts.
You need per-tenant request counts, error rates, CPU consumption, and data transfer to drive billing
reports, plan-limit enforcement, and capacity-planning — without standing up a separate metrics
backend per tenant. Analytics Engine's SQL API is the natural fit: zero-infra, queryable with
standard SQL aggregations, and keyed by tenant ID already present in your request context.

## Context

Analytics Engine (AE) accepts up to three `indexes` (high-cardinality keys), up to 20 `blobs`
(string dimensions), and up to 20 `doubles` (numeric measures) per `writeDataPoint` call. The
index is used for efficient filtering; blobs and doubles drive GROUP BY aggregations. For
multi-tenant metering the tenant ID goes in `indexes[0]`, plan tier and region in blobs, and
request/error/byte counters in doubles. AE rows are eventually consistent with ~15 s ingestion lag
and are queryable via a REST SQL endpoint that returns JSON.

## Writing Metering Data from Workers

```typescript
// src/metering-middleware.ts
export interface Env {
  METERING: AnalyticsEngineDataset;
}

export interface TenantContext {
  tenantId: string;
  planTier: "free" | "pro" | "enterprise";
  region: string;
}

export async function recordUsage(
  request: Request,
  response: Response,
  ctx: TenantContext,
  cpuMs: number,
  env: Env
): Promise<void> {
  const isError = response.status >= 500 ? 1 : 0;
  const isClientError = response.status >= 400 && response.status < 500 ? 1 : 0;
  const contentLength = Number(response.headers.get("content-length") ?? 0);

  env.METERING.writeDataPoint({
    blobs: [
      ctx.tenantId,         // blob1 – tenant
      ctx.planTier,         // blob2 – plan
      ctx.region,           // blob3 – region
      new URL(request.url).pathname.split("/")[1] ?? "", // blob4 – top-level route
      String(response.status), // blob5 – HTTP status
    ],
    doubles: [
      1,                    // double1 – request count
      isError,              // double2 – 5xx count
      isClientError,        // double3 – 4xx count
      cpuMs,                // double4 – CPU ms consumed
      contentLength,        // double5 – response bytes
    ],
    indexes: [ctx.tenantId],
  });
}
```

Wrap your existing fetch handler:

```typescript
// src/index.ts
import { recordUsage } from "./metering-middleware";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const tenantCtx = await resolveTenant(request, env); // your auth logic
    const start = Date.now();
    const response = await handleRequest(request, env, tenantCtx);
    const cpuMs = Date.now() - start; // wall-clock proxy; use cpuTime from Tail Worker for accuracy
    ctx.waitUntil(recordUsage(request, response, tenantCtx, cpuMs, env));
    return response;
  },
};
```

## Per-Tenant Usage Query

```typescript
// src/query-tenant-usage.ts
async function tenantUsageSummary(
  accountId: string,
  apiToken: string,
  tenantId: string,
  hours = 24
): Promise<void> {
  const sql = `
    SELECT
      blob1  AS tenant_id,
      blob2  AS plan_tier,
      sum(double1)             AS total_requests,
      sum(double2)             AS server_errors,
      sum(double3)             AS client_errors,
      sum(double2) / sum(double1) * 100 AS error_rate_pct,
      sum(double4)             AS total_cpu_ms,
      sum(double5)             AS total_response_bytes,
      sum(double5) / 1048576.0 AS total_response_mb
    FROM worker_metering
    WHERE
      timestamp > NOW() - INTERVAL '${hours}' HOUR
      AND blob1 = '${tenantId}'
    GROUP BY blob1, blob2
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${apiToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ query: sql }),
    }
  );
  const data = await res.json();
  console.table(data.data);
}
```

## Top-N Tenants Leaderboard

Useful for spotting runaway consumers before plan enforcement kicks in:

```typescript
async function topTenantsByRequests(
  accountId: string,
  apiToken: string,
  topN = 20
): Promise<void> {
  const sql = `
    SELECT
      blob1 AS tenant_id,
      blob2 AS plan_tier,
      sum(double1) AS requests,
      sum(double4) AS cpu_ms,
      sum(double5) AS response_bytes
    FROM worker_metering
    WHERE timestamp > NOW() - INTERVAL '1' HOUR
    GROUP BY blob1, blob2
    ORDER BY requests DESC
    LIMIT ${topN}
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    { method: "POST", headers: { Authorization: `Bearer ${apiToken}` }, body: JSON.stringify({ query: sql }) }
  );
  const { data } = await res.json();
  for (const row of data) {
    console.log(`${row.tenant_id} (${row.plan_tier}): ${row.requests} req, ${row.cpu_ms} cpu-ms`);
  }
}
```

## Plan Limit Enforcement Worker (Scheduled)

```typescript
// src/limit-enforcer.ts – runs every 5 minutes via cron
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const tenants = await fetchAllTenants(env); // your tenant registry
    for (const tenant of tenants) {
      const usage = await getTenantUsage(env, tenant.id, 60); // last 60 min
      if (usage.totalRequests > tenant.plan.hourlyRequestLimit) {
        await env.THROTTLE_KV.put(`throttle:${tenant.id}`, "1", { expirationTtl: 300 });
        console.log(`Throttling tenant ${tenant.id}: ${usage.totalRequests} req/hr`);
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## Time-Series Breakdown (Hourly Buckets)

```sql
SELECT
  toStartOfInterval(timestamp, INTERVAL '1' HOUR) AS hour_bucket,
  blob1 AS tenant_id,
  sum(double1) AS requests,
  sum(double2) AS errors
FROM worker_metering
WHERE
  timestamp > NOW() - INTERVAL '7' DAY
  AND blob1 = 'tenant-acme'
GROUP BY hour_bucket, tenant_id
ORDER BY hour_bucket ASC
```

## Anti-patterns

- **Using `blob1` for high-cardinality plan names instead of tenant IDs.** Analytics Engine indexes
  are for tenant ID (the primary filter key). Putting tenant ID in a blob and using a static string
  in the index destroys query performance.
- **Writing synchronously in the fetch handler.** `writeDataPoint` is best-effort fire-and-forget.
  Always wrap in `ctx.waitUntil()` so it does not block the response.
- **Summing doubles that should be counts.** If you store `isError` as 0/1, `sum(double2)` gives
  you the error count. Do not average this field expecting a rate — compute the rate in the SELECT.
- **One dataset per tenant.** AE supports up to ~100 datasets per account. Do not create a dataset
  per tenant; use a single dataset with tenant ID as index.

## Gotchas

- AE SQL API returns at most 500,000 rows per query. For accounts with millions of tenants querying
  over long windows, add `LIMIT` and paginate or pre-aggregate with a scheduled Worker.
- The `indexes` field is limited to 96 bytes each. Tenant IDs longer than 96 bytes must be hashed
  (SHA-256 truncated to 16 hex chars works well).
- `writeDataPoint` failures are silent — the Worker does not throw. Instrument your Tail Worker to
  count dropped metering rows via a separate low-volume AE dataset.
- AE data is retained for 31 days by default. For billing periods longer than a month, export daily
  rollups to R2 via a scheduled Worker before the data ages out.

## Verification

1. Send 10 test requests from three different synthetic tenant IDs.
2. Wait 60 seconds, then query:
   ```sql
   SELECT blob1, sum(double1) FROM worker_metering
   WHERE timestamp > NOW() - INTERVAL '5' MINUTE
   GROUP BY blob1
   ```
   Expect three rows each with count 10.
3. Send requests that return 500 errors; verify `sum(double2)` increments.
4. Confirm the top-N query returns tenants ordered by request count descending.

## Related

- `cloudflare-analytics-engine.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `cloudflare-analytics-engine-grafana-dashboard.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `sli-slo-error-budget-d1-tracking.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/limits/
