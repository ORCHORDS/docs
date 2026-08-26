# R2 Storage Usage Analytics Engine Cost Monitoring

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project stores user-uploaded media and cached content in R2. Without storage byte tracking, the team discovers cost overruns only when the monthly bill arrives. R2 charges for stored GB-months, Class A operations (PUT/POST), and Class B operations (GET/HEAD); none of these appear in real-time dashboards by default. By writing periodic storage snapshots and per-operation metrics to Analytics Engine, the team can project monthly costs mid-cycle and alert when growth exceeds budget.

## Context

Cloudflare does not push real-time R2 storage metrics to Analytics Engine automatically. The approach here uses a Cron Trigger Worker that calls the Cloudflare API's R2 usage endpoint on a schedule and writes the result as a data point. Per-operation metrics are emitted from the same Worker that performs R2 reads and writes, using `ctx.waitUntil` to avoid adding latency. Analytics Engine then provides a queryable time series for dashboards and spend forecasting.

## Section 1 — Instrumentation: Per-Operation Cost Tagging

Wrap all R2 operations in a thin cost-tracking layer. Cloudflare bills per-operation class, so classify every call and write a data point with approximate cost in USD micro-cents for easy summation.

```typescript
// workers/src/r2-instrumented.ts
import { Env } from "./types";

// Pricing as of 2026 (check for updates: developers.cloudflare.com/r2/pricing/)
const CLASS_A_COST_USD = 4.50 / 1_000_000;  // per operation
const CLASS_B_COST_USD = 0.36 / 1_000_000;  // per operation
const STORAGE_GB_MONTH_USD = 0.015;          // per GB-month

type R2OpClass = "A" | "B";

const OP_CLASS: Record<string, R2OpClass> = {
  put: "A",
  createMultipartUpload: "A",
  uploadPart: "A",
  completeMultipartUpload: "A",
  delete: "A",
  get: "B",
  head: "B",
  list: "B",
};

export async function r2Op<T>(
  opName: keyof typeof OP_CLASS,
  bucket: R2Bucket,
  fn: () => Promise<T>,
  env: Env,
  ctx: ExecutionContext,
  meta: { key?: string; bytes?: number } = {}
): Promise<T> {
  const opClass = OP_CLASS[opName] ?? "B";
  const costUsd = opClass === "A" ? CLASS_A_COST_USD : CLASS_B_COST_USD;

  const start = Date.now();
  const result = await fn();
  const latencyMs = Date.now() - start;

  ctx.waitUntil(
    Promise.resolve(
      env.ANALYTICS_ENGINE.writeDataPoint({
        blobs: [
          "r2_operation",         // blob1: metric type
          opName,                 // blob2: operation name
          opClass,                // blob3: billing class A or B
          meta.key?.split("/")[0] ?? "root",  // blob4: key prefix (first segment)
          env.ENVIRONMENT,        // blob5: environment
          env.R2_BUCKET_NAME,     // blob6: bucket name
        ],
        doubles: [
          1,                      // double1: operation count (always 1)
          latencyMs,              // double2: latency ms
          meta.bytes ?? 0,        // double3: bytes transferred
          costUsd * 1e9,          // double4: cost in nano-USD (avoid float precision loss)
        ],
        indexes: [opName],
      })
    )
  );

  return result;
}

// Convenience wrappers
export async function r2Put(
  bucket: R2Bucket,
  key: string,
  value: ReadableStream | ArrayBuffer | string,
  env: Env,
  ctx: ExecutionContext,
  bytes = 0
): Promise<R2Object | null> {
  return r2Op("put", bucket, () => bucket.put(key, value), env, ctx, { key, bytes });
}

export async function r2Get(
  bucket: R2Bucket,
  key: string,
  env: Env,
  ctx: ExecutionContext
): Promise<R2ObjectBody | null> {
  return r2Op("get", bucket, () => bucket.get(key), env, ctx, { key });
}
```

## Section 2 — Cron Worker: Storage Snapshot via Cloudflare API

Poll the R2 usage endpoint every hour to snapshot total bytes stored. This gives the GB-month time series needed for cost projection.

```typescript
// workers/src/r2-storage-snapshot.ts
interface Env {
  ANALYTICS_ENGINE: AnalyticsEngineDataset;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  R2_BUCKET_NAME: string;
  ENVIRONMENT: string;
}

interface R2UsageRow {
  storageBytes: number;
  objectCount: number;
  uploadBytes: number;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const url =
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}` +
      `/r2/buckets/${env.R2_BUCKET_NAME}/usage`;

    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
    });

    if (!resp.ok) {
      console.error("R2 usage API error", resp.status, await resp.text());
      return;
    }

    const { result } = await resp.json<{ result: R2UsageRow }>();
    const storageGb = result.storageBytes / 1e9;

    // Estimate cost-to-date for this month using stored GB × elapsed fraction
    const now = new Date();
    const dayOfMonth = now.getUTCDate();
    const daysInMonth = new Date(now.getUTCFullYear(), now.getUTCMonth() + 1, 0).getUTCDate();
    const monthFraction = dayOfMonth / daysInMonth;
    const estimatedMonthlyStorageCostUsd = storageGb * 0.015 * monthFraction;

    env.ANALYTICS_ENGINE.writeDataPoint({
      blobs: [
        "r2_storage_snapshot",
        env.R2_BUCKET_NAME,
        env.ENVIRONMENT,
      ],
      doubles: [
        result.storageBytes,                    // double1: raw bytes
        storageGb,                              // double2: GB
        result.objectCount,                     // double3: object count
        estimatedMonthlyStorageCostUsd * 1e6,  // double4: estimated cost micro-USD
      ],
      indexes: [env.R2_BUCKET_NAME],
    });
  },
};
```

wrangler.toml cron configuration:

```toml
[triggers]
crons = ["0 * * * *"]  # every hour
```

## Section 3 — Alerting: Storage Budget Burn Rate

Alert when projected monthly cost exceeds a budget threshold before the month ends.

```typescript
// workers/src/r2-cost-alert.ts
interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  SLACK_WEBHOOK_URL: string;
  MONTHLY_BUDGET_USD: string; // string because env vars are strings
}

const AE_PROJECTION_QUERY = `
  SELECT
    MAX(double4) / 1e6 AS current_estimated_monthly_usd,
    MAX(double2)       AS current_gb
  FROM analytics_engine_dataset
  WHERE blob1 = 'r2_storage_snapshot'
    AND timestamp > NOW() - INTERVAL '2' HOUR
`;

export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    const budget = parseFloat(env.MONTHLY_BUDGET_USD);

    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
        body: JSON.stringify({ query: AE_PROJECTION_QUERY }),
      }
    );

    const { data } = await resp.json<{
      data: { current_estimated_monthly_usd: number; current_gb: number }[];
    }>();

    const row = data?.[0];
    if (!row) return;

    const burnPct = (row.current_estimated_monthly_usd / budget) * 100;

    if (burnPct >= 80) {
      await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `*R2 Storage Cost Alert* — ${burnPct.toFixed(1)}% of monthly budget ($${budget}) consumed. ` +
            `Current storage: ${row.current_gb.toFixed(2)} GB. ` +
            `Projected cost: $${row.current_estimated_monthly_usd.toFixed(2)}.`,
        }),
      });
    }
  },
};
```

## Section 4 — Dashboard Queries

```sql
-- Storage growth trend (hourly snapshots, last 7 days)
SELECT
  DATE_TRUNC('hour', timestamp) AS hour,
  MAX(double2) AS storage_gb,
  MAX(double3) AS object_count,
  MAX(double4) / 1e6 AS estimated_cost_usd
FROM analytics_engine_dataset
WHERE blob1 = 'r2_storage_snapshot'
  AND timestamp > NOW() - INTERVAL '7' DAY
GROUP BY 1
ORDER BY 1;

-- Operation costs by class (last 24 hours)
SELECT
  blob3 AS op_class,
  blob2 AS op_name,
  SUM(double1) AS op_count,
  SUM(double4) / 1e9 AS total_cost_usd,
  SUM(double3) / 1e9 AS total_gb_transferred
FROM analytics_engine_dataset
WHERE blob1 = 'r2_operation'
  AND timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY 1, 2
ORDER BY 4 DESC;

-- Top key prefixes by operation cost
SELECT
  blob4 AS key_prefix,
  SUM(double4) / 1e9 AS cost_usd,
  COUNT(*) AS ops
FROM analytics_engine_dataset
WHERE blob1 = 'r2_operation'
  AND timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;
```

## Anti-patterns

- Polling the R2 usage API more frequently than hourly — the API reflects near-real-time storage but is rate-limited; hourly snapshots are sufficient for cost monitoring.
- Storing raw per-byte costs as floats in Analytics Engine doubles — use nano-USD or micro-USD integers to avoid floating-point precision loss across many writes.
- Counting all R2 GETs as equal cost — presigned URL downloads from R2 public buckets are free; only API-authenticated GETs through a Worker are billed as Class B operations.
- Forgetting egress costs — R2 egress to the Internet is free; egress to non-Cloudflare origins via Workers counts as Worker subrequest bandwidth, not R2 cost.

## Gotchas

- `r2/buckets/{name}/usage` endpoint requires the `Workers R2 Storage:Read` API token permission, not just `Workers Scripts:Read`.
- The storage bytes value from the API reflects the true object size; multipart uploads are counted once the upload is complete, not at each part.
- Analytics Engine `double` columns are 64-bit floats; storing nano-USD as integers up to ~9 × 10^18 is safe for years of budget tracking.
- `ctx.waitUntil` in Workers is capped at 30 seconds after the last response is sent; very high-throughput Workers may queue more `writeDataPoint` calls than can complete — shed load by sampling at high operation rates.
- The `R2_BUCKET_NAME` env var must match the binding name in `wrangler.toml`, not the bucket's display name.

## Verification

1. Upload a 10 MB object via the instrumented `r2Put` wrapper.
2. Query Analytics Engine: `SELECT SUM(double3) FROM ae WHERE blob1 = 'r2_operation' AND blob2 = 'put'` — expect ~10 000 000 bytes.
3. Trigger the Cron Worker manually with `wrangler dev --test-scheduled`.
4. Query: `SELECT MAX(double2) FROM ae WHERE blob1 = 'r2_storage_snapshot'` — expect ≥ 0.01 GB.
5. Set `MONTHLY_BUDGET_USD=0.001` and trigger the alert Worker — confirm Slack message fires.

## Related

- `/documentation/docs/policies/monitoring/r2-bandwidth-usage-analytics-engine.md`
- `/documentation/docs/policies/monitoring/cloudflare-billing-cost-anomaly-detection.md`
- `/documentation/docs/policies/monitoring/analytics-engine-multi-tenant-usage-metering.md`
- `/documentation/docs/policies/monitoring/cost-monitoring-dashboards.md`
- `/documentation/docs/policies/monitoring/observability-cost-control.md`

## Sources

- https://developers.cloudflare.com/r2/pricing/
- https://developers.cloudflare.com/api/operations/r2-get-usage
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
