# Cloudflare Analytics Engine Dataset Terraform Init

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Workers emit custom metrics (API latency, cache hit rates, business events), but they are
currently written to KV or shipped to a third-party analytics provider. You want Cloudflare
Analytics Engine (AE) as a zero-latency, SQL-queryable sink that scales with your Worker fleet.
Provisioning the dataset binding through the dashboard is error-prone at scale; you need a
reproducible Terraform pattern for AE dataset bindings and the associated Workers scripts.

## Context

Cloudflare Analytics Engine is a time-series columnar store exposed to Workers via a `writeDataPoint`
API. There is no separate "create dataset" API call — the dataset is implicitly created the first
time a Worker writes to it. Terraform's job is to declare the **binding** (the logical name the
Worker uses to reference the dataset) within the `cloudflare_workers_script` resource, and to
manage the Worker itself. Querying is done via the GraphQL Analytics API or the HTTP SQL endpoint
(`/v4/accounts/:id/analytics_engine/sql`).

---

## 1. Workers Script with Analytics Engine Binding

```hcl
# analytics-worker.tf
variable "cloudflare_account_id" { type = string }
variable "zone_id"               { type = string }

resource "cloudflare_workers_script" "api_metrics" {
  account_id = var.cloudflare_account_id
  name       = "api-metrics-collector"
  content    = file("${path.module}/dist/metrics.js")

  analytics_engine_binding {
    name    = "METRICS"        # env binding name inside the Worker
    dataset = "api_metrics"    # AE dataset name (created on first write)
  }

  analytics_engine_binding {
    name    = "ERRORS"
    dataset = "api_errors"
  }
}
```

Multiple bindings map to multiple independent datasets within the same Worker. Dataset names must
be unique per account and follow `[a-z0-9_]+` (lowercase, digits, underscores only).

---

## 2. Worker Metrics Emission

```typescript
// src/metrics.ts
interface Env {
  METRICS: AnalyticsEngineDataset;
  ERRORS: AnalyticsEngineDataset;
}

interface RequestMeta {
  route: string;
  statusCode: number;
  durationMs: number;
  cacheHit: boolean;
  region: string;
}

function recordRequest(meta: RequestMeta, env: Env): void {
  env.METRICS.writeDataPoint({
    blobs: [meta.route, meta.region],          // up to 20 blob columns
    doubles: [meta.durationMs, meta.statusCode], // up to 20 double columns
    indexes: [meta.route],                      // 1 index for partitioning
  });
}

function recordError(error: Error, route: string, env: Env): void {
  env.ERRORS.writeDataPoint({
    blobs: [route, error.name, error.message.slice(0, 255)],
    doubles: [Date.now()],
    indexes: [route],
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);

    try {
      const response = await handleRequest(request, env);
      ctx.waitUntil(
        Promise.resolve(
          recordRequest(
            {
              route: url.pathname,
              statusCode: response.status,
              durationMs: Date.now() - start,
              cacheHit: response.headers.get("cf-cache-status") === "HIT",
              region: request.cf?.colo ?? "unknown",
            },
            env
          )
        )
      );
      return response;
    } catch (err) {
      recordError(err as Error, url.pathname, env);
      return new Response("Internal error", { status: 500 });
    }
  },
};

async function handleRequest(request: Request, _env: Env): Promise<Response> {
  return new Response("ok");
}
```

---

## 3. Route Binding

```hcl
# routes.tf
resource "cloudflare_worker_route" "api_metrics" {
  zone_id     = var.zone_id
  pattern     = "api.example.com/*"
  script_name = cloudflare_workers_script.api_metrics.name
}
```

---

## 4. Querying Analytics Engine via SQL API

```typescript
// src/query-ae.ts  (runs server-side, not in a Worker)
const CF_ACCOUNT = process.env.CF_ACCOUNT_ID!;
const CF_TOKEN   = process.env.CF_API_TOKEN!;

export async function queryLatencyP95(dataset = "api_metrics"): Promise<unknown> {
  const sql = `
    SELECT
      blob1 AS route,
      quantilesMerge(0.95)(double1) AS p95_ms,
      count() AS requests
    FROM ${dataset}
    WHERE timestamp >= now() - INTERVAL '1' HOUR
    GROUP BY route
    ORDER BY p95_ms DESC
    LIMIT 20
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${CF_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  if (!res.ok) throw new Error(`AE query failed: ${await res.text()}`);
  return res.json();
}
```

---

## 5. Multi-Dataset Module Pattern

```hcl
# modules/ae-worker/variables.tf
variable "account_id"    { type = string }
variable "worker_name"   { type = string }
variable "worker_bundle" { type = string }
variable "datasets" {
  type = map(string)  # binding_name -> dataset_name
  default = {}
}

# modules/ae-worker/main.tf
resource "cloudflare_workers_script" "this" {
  account_id = var.account_id
  name       = var.worker_name
  content    = var.worker_bundle

  dynamic "analytics_engine_binding" {
    for_each = var.datasets
    content {
      name    = analytics_engine_binding.key
      dataset = analytics_engine_binding.value
    }
  }
}
```

```hcl
# env/prod/main.tf
module "payments_worker" {
  source      = "../../modules/ae-worker"
  account_id  = var.cloudflare_account_id
  worker_name = "payments-api"
  worker_bundle = file("dist/payments.js")
  datasets = {
    METRICS  = "payments_metrics_prod"
    ERRORS   = "payments_errors_prod"
    CHECKOUTS = "checkout_funnel_prod"
  }
}
```

---

## Anti-patterns

- **Writing to AE inside `await`ed promises without `waitUntil`.** `writeDataPoint` is
  fire-and-forget; if you `await` it inside the request path, you add latency for no benefit.
  Always schedule it via `ctx.waitUntil`.
- **Storing more than 20 blobs or doubles.** AE silently drops columns past the limit. Schema
  your data carefully before launch.
- **Using AE for transactional data.** AE is append-only with eventual consistency and no
  deduplication. For billing-critical data, use D1 or an external OLTP system.
- **Querying AE from inside a Worker via the HTTP SQL API.** This introduces a network round-trip
  on every request. Query AE from your backend or a Scheduled Worker.

---

## Gotchas

- Dataset names are created implicitly on first write. Running `terraform plan` against an
  account with no writes yet will succeed but no dataset will exist until the Worker actually runs.
- The `analytics_engine_binding` block is replace-in-place: changing the `dataset` field does not
  migrate historical data — the old dataset remains queryable but the Worker writes to the new one.
- AE data retention is 31 days (as of 2026-08). Data older than that is automatically purged.
- `indexes` accepts exactly one value; attempting to pass multiple will cause the write to fail
  silently. Use `blobs` for additional categorical dimensions.
- AE SQL uses ClickHouse-compatible syntax but does not support all ClickHouse functions. Test
  queries in the Cloudflare dashboard SQL explorer before embedding them in application code.

---

## Verification

```bash
# Confirm binding is declared in the deployed Worker
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/api-metrics-collector/bindings" \
  | jq '.result[] | select(.type=="analytics_engine") | {name, dataset}'

# Check dataset has received writes (returns rows if data exists)
curl -s -X POST \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT count() FROM api_metrics WHERE timestamp >= now() - INTERVAL '\''5'\'' MINUTE"}' \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql"

# Terraform plan shows no drift
terraform plan -detailed-exitcode
```

---

## Related

- `workers-analytics-billing-monitoring.md`
- `cloudflare-workers-cost-modeling-d1-analytics.md`
- `terraform-cloudflare-provider-workers-d1.md`
- `cloudflare-logpush-terraform-pipeline.md`
- `opentelemetry-collector-config.md`

---

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/get-started/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/workers_script
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
