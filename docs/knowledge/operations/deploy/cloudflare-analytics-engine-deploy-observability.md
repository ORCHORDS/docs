# Cloudflare Analytics Engine — Deploy-Time Observability and Traffic Attribution

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You deploy a new Worker version and want to know within minutes whether the new version is introducing elevated error rates, latency spikes, or unexpected traffic patterns — without relying on an external observability platform (Datadog, Grafana, etc.) and without polling `wrangler tail` manually. Cloudflare's built-in Workers metrics dashboard has a 1-minute granularity floor and does not let you slice by deploy version, region, or custom business dimensions.

Use cases this pattern covers:

- **Deploy health gates**: query error rate per Worker version in the 5 minutes following deploy; automatically roll back if the rate exceeds a threshold.
- **Gradual rollout confidence**: during a Worker Versions percentage split, compare error rate between the old and new version in real time.
- **Mobile app version attribution**: tag API errors by `Expo-Runtime-Version` header to detect mobile regressions triggered by a specific OTA update.
- **Business metric correlation**: track revenue-relevant events (checkout starts, payment attempts) by deploy version to catch silent business logic regressions that don't surface as HTTP errors.

## Context

Cloudflare Analytics Engine (AE) is a time-series append-only datastore built into the Workers runtime. Each write (`env.ANALYTICS.writeDataPoint(...)`) is a lightweight fire-and-forget call that costs negligible CPU time. Data is queryable within approximately 1 minute of ingestion via the SQL API at `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`.

Analytics Engine data points have three field types:
- `blobs`: up to 20 string fields (searchable, groupable, filterable).
- `doubles`: up to 20 numeric fields (summable, averageable).
- `indexes`: exactly one string used as a partitioning hint for query performance.

Data is retained for 90 days by default. There is no schema definition — fields are inferred from what you write.

AE is **not** a replacement for logs (use `wrangler tail` or Logpush for logs). It is a metrics aggregation layer designed for high-cardinality, high-volume data points.

## Step 1 — Binding and wrangler.toml configuration

```toml
# workers/api/wrangler.toml

name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "worker_requests"   # logical dataset name; auto-created on first write

[env.staging]
[[env.staging.analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "worker_requests_staging"
```

## Step 2 — Instrument the Worker with deploy-version tagging

```typescript
// workers/api/src/telemetry.ts

export interface RequestMetric {
  method: string;
  path: string;
  statusCode: number;
  durationMs: number;
  workerVersion: string;       // injected at build time via wrangler vars
  runtimeVersion: string | null; // Expo-Runtime-Version header (mobile clients)
  region: string;
  error: string | null;
}

export function writeRequestMetric(
  analytics: AnalyticsEngineDataset,
  m: RequestMetric
): void {
  analytics.writeDataPoint({
    blobs: [
      m.method,              // blob1: HTTP method
      m.path,                // blob2: normalized path (no query string)
      String(m.statusCode),  // blob3: status code as string for grouping
      m.workerVersion,       // blob4: Worker deploy version identifier
      m.runtimeVersion ?? "native",  // blob5: mobile runtime version or "native"
      m.region,              // blob6: Cloudflare colo (from request.cf.colo)
      m.error ?? "",         // blob7: error class name, empty if success
    ],
    doubles: [
      m.durationMs,          // double1: request duration in ms
      m.statusCode >= 500 ? 1 : 0,   // double2: is_error flag (1/0)
      m.statusCode >= 400 ? 1 : 0,   // double3: is_4xx flag
      1,                     // double4: request count (always 1, sum for totals)
    ],
    indexes: [m.workerVersion],  // partition by version for query efficiency
  });
}
```

Inject `workerVersion` at build time using a Wrangler variable:

```toml
# workers/api/wrangler.toml
[vars]
WORKER_VERSION = "unknown"   # overridden in CI via --var flag
```

```typescript
// workers/api/src/index.ts
export default {
  async fetch(request: Request, env: Env & { WORKER_VERSION: string }): Promise<Response> {
    const start = Date.now();
    let statusCode = 200;
    let errorClass: string | null = null;

    try {
      const response = await router(request, env);
      statusCode = response.status;
      return response;
    } catch (err: unknown) {
      statusCode = 500;
      errorClass = err instanceof Error ? err.constructor.name : "UnknownError";
      return new Response("Internal Server Error", { status: 500 });
    } finally {
      writeRequestMetric(env.ANALYTICS, {
        method: request.method,
        path: normalizePath(new URL(request.url).pathname),
        statusCode,
        durationMs: Date.now() - start,
        workerVersion: env.WORKER_VERSION,
        runtimeVersion: request.headers.get("Expo-Runtime-Version"),
        region: (request as unknown as { cf?: { colo?: string } }).cf?.colo ?? "unknown",
        error: errorClass,
      });
    }
  },
};

// Strip IDs from paths for cardinality control
function normalizePath(path: string): string {
  return path
    .replace(/\/[0-9a-f-]{8,}/gi, "/:id")   // UUIDs
    .replace(/\/\d+/g, "/:n");               // numeric IDs
}
```

In GitHub Actions, pass the version at deploy time:

```yaml
- name: Deploy Worker with version tag
  working-directory: workers/api
  run: |
    VERSION="sha-${GITHUB_SHA:0:8}-$(date +%Y%m%d%H%M%S)"
    npx wrangler deploy --env production --var "WORKER_VERSION=$VERSION"
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

## Step 3 — Querying Analytics Engine post-deploy

Use the AE SQL API to run deploy-health queries within minutes of deploy.

### Error rate by Worker version (last 10 minutes)

```bash
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "
      SELECT
        blob4 AS worker_version,
        SUM(double4) AS total_requests,
        SUM(double2) AS total_errors,
        ROUND(SUM(double2) / SUM(double4) * 100, 2) AS error_rate_pct,
        AVG(double1) AS avg_duration_ms
      FROM worker_requests
      WHERE timestamp > NOW() - INTERVAL '\''10'\'' MINUTE
      GROUP BY worker_version
      ORDER BY total_requests DESC
    "
  }' | jq '.data'
```

### Error breakdown by path for new version

```bash
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"
      SELECT
        blob2 AS path,
        blob3 AS status_code,
        blob7 AS error_class,
        SUM(double4) AS count
      FROM worker_requests
      WHERE timestamp > NOW() - INTERVAL '10' MINUTE
        AND blob4 = 'sha-abc12345-20260822143000'
        AND double2 = 1
      GROUP BY path, status_code, error_class
      ORDER BY count DESC
      LIMIT 20
    \"
  }" | jq '.data'
```

### Mobile version error attribution

```bash
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "
      SELECT
        blob5 AS expo_runtime_version,
        SUM(double4) AS requests,
        SUM(double2) AS errors,
        ROUND(SUM(double2) / SUM(double4) * 100, 2) AS error_rate_pct
      FROM worker_requests
      WHERE timestamp > NOW() - INTERVAL '\''60'\'' MINUTE
        AND blob5 != '\''native'\''
      GROUP BY expo_runtime_version
      ORDER BY requests DESC
    "
  }' | jq '.data'
```

## Step 4 — Automated deploy gate using AE

After deploying, run this as a CI step or a post-deploy Cron Trigger:

```typescript
// workers/deploy-gate/src/index.ts
// Scheduled Worker that checks AE post-deploy and rolls back if needed

interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  CURRENT_VERSION: string;
  ERROR_RATE_THRESHOLD: string;  // e.g. "5" for 5%
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const threshold = parseFloat(env.ERROR_RATE_THRESHOLD);

    const query = `
      SELECT
        SUM(double2) / SUM(double4) * 100 AS error_rate_pct,
        SUM(double4) AS total_requests
      FROM worker_requests
      WHERE timestamp > NOW() - INTERVAL '5' MINUTE
        AND blob4 = '${env.CURRENT_VERSION}'
    `;

    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query }),
      }
    );

    const data = await resp.json<{
      data: Array<{ error_rate_pct: number; total_requests: number }>;
    }>();

    const row = data.data[0];
    if (!row || row.total_requests < 50) {
      console.log("Insufficient traffic for gate decision, skipping");
      return;
    }

    if (row.error_rate_pct > threshold) {
      console.error(`Error rate ${row.error_rate_pct}% exceeds threshold ${threshold}% — triggering rollback`);
      // Call Wrangler API or a webhook to trigger rollback pipeline
      await fetch(env.ROLLBACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          version: env.CURRENT_VERSION,
          error_rate: row.error_rate_pct,
          reason: "Analytics Engine gate triggered",
        }),
      });
    } else {
      console.log(`Deploy healthy: error rate ${row.error_rate_pct}% (${row.total_requests} requests)`);
    }
  },
};
```

```toml
# workers/deploy-gate/wrangler.toml
[triggers]
crons = ["* * * * *"]   # run every minute for 10 minutes post-deploy, then disable
```

## Step 5 — Grafana / dashboard integration

Export AE data to Grafana via a scheduled Worker that writes to a Grafana Loki or InfluxDB push endpoint, or query the AE SQL API directly from a Grafana JSON datasource plugin. For teams using Cloudflare-native tooling only, the Cloudflare dashboard's Workers Analytics tab surfaces the AE-backed metrics you write automatically.

For a lightweight HTML analytics dashboard as an internal artifact:

```typescript
// workers/analytics-dashboard/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const [errorRates, topPaths] = await Promise.all([
      queryAE(env, "SELECT blob4 AS version, ROUND(SUM(double2)/SUM(double4)*100,2) AS err_pct FROM worker_requests WHERE timestamp > NOW() - INTERVAL '60' MINUTE GROUP BY version ORDER BY err_pct DESC LIMIT 10"),
      queryAE(env, "SELECT blob2 AS path, SUM(double4) AS reqs FROM worker_requests WHERE timestamp > NOW() - INTERVAL '60' MINUTE GROUP BY path ORDER BY reqs DESC LIMIT 10"),
    ]);

    return new Response(renderDashboard(errorRates, topPaths), {
      headers: { "Content-Type": "text/html" },
    });
  },
};
```

## Anti-patterns

- **High-cardinality blobs**: Never write user IDs, full URLs with query strings, or UUIDs as blobs directly. AE groups by blob value; unbounded cardinality makes queries useless and may hit per-dataset cardinality limits.
- **Calling `writeDataPoint` in a `waitUntil` race you don't track**: AE writes are fire-and-forget. If the Worker is evicted before `writeDataPoint` completes, the data point is lost silently. Fire AE writes before the response is returned, or confirm they're in `ctx.waitUntil`.
- **Using AE as a log store**: AE aggregates well; it is not queryable by individual `messageId`. For per-request tracing, use Logpush or `wrangler tail`.
- **Comparing versions with different traffic volumes**: A new version that handles 100 requests looks worse or better than an old one with 100,000 requests. Apply a minimum traffic threshold before making rollback decisions.
- **Writing to the same AE dataset from staging and production Workers**: Staging traffic pollutes production metrics. Use separate dataset names per environment.

## Gotchas

- AE data is ingested with approximately 1-minute delay. A deploy gate that queries within the first 60 seconds post-deploy will see no data for the new version and may pass the gate prematurely. Add a `sleep 90` or poll-until-data-exists check before the gate query.
- The AE SQL API returns `null` for aggregates over zero rows. Guard against `null` division in your gate logic.
- Analytics Engine does not support `UPDATE` or `DELETE`. Incorrect data points cannot be retracted. Use a correction point (write another data point with a flag) rather than trying to undo.
- The free Workers plan limits AE to 100,000 data points per day. At 1 data point per request, this limits instrumented traffic to ~70 RPS before additional cost. Check your plan limits before instrumenting high-traffic endpoints.
- AE datasets persist until manually deleted via the API. After deprecating a Worker, remember to stop writes to avoid accumulating unbounded data.

## Verification

```bash
# Confirm AE is receiving data within 2 minutes of first request
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT COUNT() AS total FROM worker_requests WHERE timestamp > NOW() - INTERVAL '\''5'\'' MINUTE"}' \
  | jq '.data[0].total'

# List all AE datasets in the account
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/datasets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[].name'

# Tail Worker to confirm writeDataPoint calls are firing
npx wrangler tail orchords-api --env production --format json | \
  jq 'select(.logs[].message | contains("Analytics"))'
```

## Related

- `deployment-metrics-tracking.md`
- `post-deploy-monitoring-checklist.md`
- `worker-versioning-gradual-rollout.md`
- `canary-workers-gradual-traffic-split.md`
- `deploy-gate-e2e-tests-playwright-pages.md`
- `expo-eas-ota-workers-api-coordinated-release.md`
- `slo-alerting-thresholds.md`

## Sources

- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Analytics Engine Workers binding: https://developers.cloudflare.com/analytics/analytics-engine/binding/
- Workers limits: https://developers.cloudflare.com/workers/platform/limits/
