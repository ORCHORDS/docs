# Pulumi Cloudflare Analytics Engine Dataset Configuration

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Workers emit custom telemetry — request latency, feature flags hit
counts, per-tenant error rates — and you want to query it with SQL rather than pushing
to an external OLAP store. You need IaC (Pulumi) to bind Analytics Engine datasets to
Workers, and typed TypeScript helpers for writing events and querying via the AE SQL API.

---

## Context

Cloudflare Analytics Engine (AE) is a time-series columnar store built into the Workers
runtime. Data is written via a `dataset.writeDataPoint()` call inside a Worker; queries
run through the AE SQL API at `https://api.cloudflare.com/client/v4/accounts/{id}/analytics_engine/sql`.

Key constraints:
- Max 20 blobs (string columns) per data point, each ≤ 1 KB.
- Max 20 doubles (numeric columns) per data point.
- Writes are fire-and-forget — no acknowledgement, no backpressure.
- The dataset binding name in the Worker is the access key; the actual dataset name is
  configured in Pulumi / Terraform.
- AE is enabled per account via the Workers Paid plan; no separate resource to create.

Pulumi resource: `cloudflare.WorkersAnalyticsEngineDataset` is **not** a dedicated
Pulumi resource (as of v5.30) — the dataset is implicitly created when the first data
point is written. The only IaC surface is the **binding** declared on `WorkersScript`.

---

## 1. Provider Setup

```typescript
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";
import * as fs from "fs";
import * as path from "path";

const cfg       = new pulumi.Config("cloudflare");
const accountId = cfg.requireSecret("accountId");
```

---

## 2. Binding Analytics Engine Datasets to a Worker

```typescript
const analyticsWorker = new cloudflare.WorkersScript("analytics-writer", {
  accountId,
  name: "analytics-writer",
  content: new pulumi.asset.FileAsset(
    path.join(__dirname, "dist/analytics-writer/index.js"),
  ),
  module: true,

  analyticsEngineBindings: [
    {
      name:    "REQUEST_ANALYTICS",   // env.REQUEST_ANALYTICS inside the Worker
      dataset: "request_analytics",   // AE dataset name (auto-created on first write)
    },
    {
      name:    "ERROR_ANALYTICS",
      dataset: "error_analytics",
    },
  ],
});

export const workerName = analyticsWorker.name;
```

Multiple datasets per worker are supported; each binding name maps to a different
dataset. Dataset names are lowercase, underscores allowed, max 64 chars.

---

## 3. Writing Data Points from a Worker

```typescript
// src/analytics-writer/types.ts
interface Env {
  REQUEST_ANALYTICS: AnalyticsEngineDataset;
  ERROR_ANALYTICS:   AnalyticsEngineDataset;
}

// src/analytics-writer/index.ts
export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url    = new URL(req.url);
    const t0     = Date.now();
    const res    = await handleRequest(req, env);
    const latMs  = Date.now() - t0;

    // Fire-and-forget — do not await
    ctx.waitUntil(
      Promise.resolve().then(() => {
        env.REQUEST_ANALYTICS.writeDataPoint({
          blobs:   [
            url.pathname,                       // blob1: path
            req.headers.get("cf-ray") ?? "",    // blob2: ray ID
            req.cf?.country as string ?? "",    // blob3: country
            res.status.toString(),              // blob4: HTTP status class
          ],
          doubles: [
            latMs,                              // double1: latency ms
            Number(req.headers.get("content-length") ?? 0),  // double2: body size
          ],
          indexes: [url.pathname],              // high-cardinality index (optional)
        });
      }),
    );

    return res;
  },
};

async function handleRequest(_req: Request, _env: Env): Promise<Response> {
  return new Response("ok");
}
```

---

## 4. Querying AE via the SQL API (from a Worker or CI)

```typescript
// src/lib/ae-query.ts

const AE_SQL_BASE = "https://api.cloudflare.com/client/v4/accounts";

interface AeQueryResult<T = Record<string, unknown>> {
  data: T[];
  rows_read: number;
  rows_written: number;
  meta: {
    name: string;
    type: string;
  }[];
}

export async function queryAnalyticsEngine<T = Record<string, unknown>>(
  accountId: string,
  apiToken: string,
  sql: string,
): Promise<AeQueryResult<T>> {
  const res = await fetch(`${AE_SQL_BASE}/${accountId}/analytics_engine/sql`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query: sql }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`AE SQL query failed (HTTP ${res.status}): ${body}`);
  }
  return res.json<AeQueryResult<T>>();
}
```

```typescript
// Usage — p99 latency over last hour by path
const result = await queryAnalyticsEngine(accountId, token, `
  SELECT
    blob1                          AS path,
    quantilesTDigest(0.99)(double1) AS p99_ms,
    count()                        AS requests
  FROM request_analytics
  WHERE timestamp >= NOW() - INTERVAL '1' HOUR
  GROUP BY path
  ORDER BY requests DESC
  LIMIT 20
`);
console.table(result.data);
```

---

## 5. Pulumi Stack Outputs for Cross-Stack Reference

```typescript
// Export dataset names so app stacks can reference them
export const requestAnalyticsDataset = pulumi.output("request_analytics");
export const errorAnalyticsDataset   = pulumi.output("error_analytics");

// In a monitoring stack
const infraStack = new pulumi.StackReference("org/infra/prod");
const dataset    = infraStack.getOutput("requestAnalyticsDataset");

// Pass dataset name to a query Worker that reads it as an env var
const queryWorker = new cloudflare.WorkersScript("ae-query-worker", {
  accountId,
  name: "ae-query-worker",
  content: new pulumi.asset.FileAsset("dist/query/index.js"),
  module: true,
  analyticsEngineBindings: [
    { name: "METRICS", dataset: dataset },
  ],
  plainTextBindings: [
    { name: "AE_DATASET_NAME", text: dataset },
  ],
});
```

---

## 6. Scheduled Rollup Worker — Aggregate Into D1

```typescript
// Pair AE with D1: AE for hot telemetry, D1 for hourly rollups
const rollupWorker = new cloudflare.WorkersScript("ae-rollup", {
  accountId,
  name: "ae-rollup",
  content: new pulumi.asset.FileAsset("dist/rollup/index.js"),
  module: true,
  analyticsEngineBindings: [
    { name: "METRICS",  dataset: "request_analytics" },
  ],
  d1DatabaseBindings: [
    { binding: "DB", databaseId: metricsD1.id },
  ],
});

// cron trigger: every hour
new cloudflare.WorkerCronTrigger("ae-rollup-cron", {
  accountId,
  scriptName: rollupWorker.name,
  schedules: ["0 * * * *"],
});
```

---

## Anti-patterns

- **Awaiting `writeDataPoint()`** — it returns `void`; awaiting does nothing and may
  cause confusion. Always fire inside `ctx.waitUntil()`.
- **Using AE as a transactional store** — AE is append-only, eventually consistent,
  and has no delete/update. Use D1 for mutable state.
- **More than 20 blobs or doubles** — the runtime silently truncates excess fields.
  Define a fixed schema and document field indices.
- **High-cardinality `indexes` fields** — the `indexes` array is for accelerating
  GROUP BY; using a UUID or ray ID here degrades query performance.
- **Querying without a time filter** — full table scans over large datasets hit query
  timeouts (60 s). Always bound queries with `WHERE timestamp >= ...`.

---

## Gotchas

- AE datasets appear in the dashboard only after the first data point is written — the
  Pulumi binding alone does not create a visible dataset.
- The SQL dialect is ClickHouse-compatible but not identical — `quantilesTDigest` is
  ClickHouse syntax; standard `PERCENTILE_CONT` is not supported.
- `blob` field ordering is fixed by call order, not by name — document the schema as
  numbered comments in code.
- The AE SQL API returns results in JSON Lines format for large queries; the
  `Content-Type` header is `application/json` regardless — parse accordingly.
- AE data is retained for 31 days on the default plan; no configurable retention.
- Writes from `curl`/REST are not supported; the only write path is the Worker runtime
  binding.

---

## Verification

```bash
# Confirm binding appears in worker details
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/analytics-writer/bindings" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | select(.type=="analytics_engine")'

# Run a quick count query
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT count() FROM request_analytics WHERE timestamp >= NOW() - INTERVAL '\''10'\'' MINUTE"}' \
  | jq '.data'
```

---

## Related

- `cloudflare-analytics-engine-terraform-init.md`
- `pulumi-cloudflare-d1-database-iac.md`
- `cloudflare-workers-cost-modeling-d1-analytics.md`
- `workers-analytics-billing-monitoring.md`
- `workers-opentelemetry-tail-workers.md`

---

## Sources

- AE runtime API: https://developers.cloudflare.com/analytics/analytics-engine/worker-api/
- AE SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Pulumi CF WorkersScript: https://www.pulumi.com/registry/packages/cloudflare/api-docs/workersscript/
- AE SQL reference: https://developers.cloudflare.com/analytics/analytics-engine/sql-reference/
