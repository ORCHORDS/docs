# Infrastructure Cost Attribution Tracking with Workers + Analytics Engine

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Cloudflare Workers bill grows every month and you cannot tell which team, service, or environment is responsible. You need per-request cost attribution: tag each request with team, service, and environment labels; ingest cost metrics to Analytics Engine; query them with SQL to produce budget reports; and alert when a team exceeds its allocated budget or when costs spike unexpectedly.

## Context

Cloudflare Analytics Engine (AE) is a write-once time-series data store built into the Workers runtime. Each `writeDataPoint` call is zero-latency from the Worker's perspective (fire-and-forget). AE data is queryable via SQL through the `/v1/query` REST endpoint and supports aggregations, filtering, and time bucketing.

This guide implements:
1. Request tagging middleware that attaches team/service/environment labels
2. Cost metric calculation per request (CPU, KV reads/writes, subrequests)
3. AE ingestion via `writeDataPoint`
4. SQL cost queries for dashboards and budget reports
5. Budget alert thresholds evaluated on a cron schedule
6. Cost anomaly detection using a rolling baseline

## Solution

### Types

```typescript
// src/types.ts
export interface CostTag {
  team: string;        // e.g. "platform", "search", "ml"
  service: string;     // e.g. "example project-api", "rag-worker"
  environment: string; // "production" | "staging" | "preview"
  version?: string;    // Worker version or git SHA
}

export interface RequestCost {
  wallTimeMs: number;
  cpuTimeMs: number;
  kvReads: number;
  kvWrites: number;
  subrequests: number;
  // Estimated USD cost (approximate, based on Cloudflare pricing)
  estimatedUsdMicros: number;
}

export interface Env {
  COST_AE: AnalyticsEngineDataset;
  COST_KV: KVNamespace;   // budget thresholds and baselines
  TEAM_TAG: string;       // set per Worker deployment
  SERVICE_TAG: string;
  ENVIRONMENT: string;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;   // Analytics Engine query token
  ALERT_WEBHOOK_URL: string;
}

// Cloudflare Workers pricing (Workers Paid, as of 2024)
const PRICING = {
  requestsPer10M_usd: 0.30,      // $0.30 per 10M requests
  cpuMsPerM_usd: 0.02,           // $0.02 per 1M CPU-ms
  kvReadsPer1M_usd: 0.50,        // $0.50 per 1M KV reads
  kvWritesPer1M_usd: 5.00,       // $5.00 per 1M KV writes
  subrequestsPer1M_usd: 0.09,    // $0.09 per 1M subrequests (within Workers)
};

export function estimateCostMicros(cost: Omit<RequestCost, "estimatedUsdMicros">): number {
  const requestCost = PRICING.requestsPer10M_usd / 10_000_000;
  const cpuCost    = (cost.cpuTimeMs / 1_000_000) * PRICING.cpuMsPerM_usd;
  const kvRCost    = (cost.kvReads   / 1_000_000) * PRICING.kvReadsPer1M_usd;
  const kvWCost    = (cost.kvWrites  / 1_000_000) * PRICING.kvWritesPer1M_usd;
  const srCost     = (cost.subrequests / 1_000_000) * PRICING.subrequestsPer1M_usd;
  const totalUsd   = requestCost + cpuCost + kvRCost + kvWCost + srCost;
  return Math.round(totalUsd * 1_000_000); // microdollars for integer storage
}
```

### Cost middleware

```typescript
// src/middleware/cost.ts
import type { CostTag, RequestCost, Env } from "../types";
import { estimateCostMicros } from "../types";

export interface TrackedRequest {
  startTime: number;
  kvReads: number;
  kvWrites: number;
  subrequests: number;
}

/** Call at the start of fetch() */
export function startTracking(): TrackedRequest {
  return { startTime: Date.now(), kvReads: 0, kvWrites: 0, subrequests: 0 };
}

/** Wrap KV operations to count them */
export function trackingKv(kv: KVNamespace, tracker: TrackedRequest): KVNamespace {
  return new Proxy(kv, {
    get(target, prop) {
      const original = (target as any)[prop];
      if (typeof original !== "function") return original;
      return (...args: any[]) => {
        if (prop === "get" || prop === "getWithMetadata" || prop === "list") tracker.kvReads++;
        if (prop === "put" || prop === "delete") tracker.kvWrites++;
        return original.apply(target, args);
      };
    },
  }) as KVNamespace;
}

/** Wrap fetch() to count subrequests */
export function trackingFetch(
  tracker: TrackedRequest
): typeof fetch {
  return (input: any, init?: RequestInit) => {
    tracker.subrequests++;
    return fetch(input, init);
  };
}

/** Call at the end of fetch() — writes data point to Analytics Engine */
export function flushCost(
  env: Env,
  tracker: TrackedRequest,
  tag: CostTag,
  ctx: ExecutionContext,
  request: Request
): void {
  const wallTimeMs = Date.now() - tracker.startTime;

  // cpuTime is not directly available at runtime; approximate from wallTime
  // For accurate CPU time, use the `cpu-time` experimental flag or measure
  // before/after synchronous work.
  const cpuTimeMs = wallTimeMs; // conservative upper bound

  const cost: RequestCost = {
    wallTimeMs,
    cpuTimeMs,
    kvReads: tracker.kvReads,
    kvWrites: tracker.kvWrites,
    subrequests: tracker.subrequests,
    estimatedUsdMicros: estimateCostMicros({
      wallTimeMs,
      cpuTimeMs,
      kvReads: tracker.kvReads,
      kvWrites: tracker.kvWrites,
      subrequests: tracker.subrequests,
    }),
  };

  ctx.waitUntil(
    ingestCostDataPoint(env, tag, cost, request)
  );
}

async function ingestCostDataPoint(
  env: Env,
  tag: CostTag,
  cost: RequestCost,
  request: Request
): Promise<void> {
  const url = new URL(request.url);
  env.COST_AE.writeDataPoint({
    blobs: [
      tag.team,
      tag.service,
      tag.environment,
      tag.version ?? "unknown",
      request.method,
      url.pathname,
      String((request as any).cf?.country ?? "XX"),
    ],
    doubles: [
      cost.wallTimeMs,
      cost.cpuTimeMs,
      cost.kvReads,
      cost.kvWrites,
      cost.subrequests,
      cost.estimatedUsdMicros,
    ],
    indexes: [tag.team], // enables efficient team-scoped queries
  });
}
```

### Main Worker with cost tracking wired in

```typescript
// src/index.ts
import type { Env } from "./types";
import { startTracking, trackingKv, flushCost } from "./middleware/cost";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const tracker = startTracking();
    const kv = trackingKv(env.COST_KV, tracker);

    const tag = {
      team: env.TEAM_TAG,
      service: env.SERVICE_TAG,
      environment: env.ENVIRONMENT,
    };

    try {
      // --- Your application logic here ---
      const value = await kv.get("some-key");
      const response = new Response(`Hello from ${tag.service}: ${value}`);
      // ------------------------------------

      flushCost(env, tracker, tag, ctx, request);
      return response;
    } catch (err) {
      flushCost(env, tracker, tag, ctx, request);
      throw err;
    }
  },
};
```

### Analytics Engine SQL queries

```typescript
// src/queries.ts — run from a reporting Worker or CI script

const AE_QUERY_URL = (accountId: string) =>
  `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`;

async function runQuery(env: Env, sql: string): Promise<any> {
  const resp = await fetch(AE_QUERY_URL(env.CF_ACCOUNT_ID), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "text/plain",
    },
    body: sql,
  });
  if (!resp.ok) throw new Error(`AE query failed: ${await resp.text()}`);
  return resp.json();
}

/** Cost by team for current month */
export async function costByTeam(env: Env): Promise<any> {
  return runQuery(env, `
    SELECT
      blob1 AS team,
      SUM(_sample_interval * double6) / 1000000.0 AS estimated_usd,
      SUM(_sample_interval) AS total_requests,
      AVG(double1) AS avg_wall_time_ms
    FROM COST_AE
    WHERE timestamp >= toStartOfMonth(now())
    GROUP BY team
    ORDER BY estimated_usd DESC
  `);
}

/** Cost by service within a team */
export async function costByService(env: Env, team: string): Promise<any> {
  return runQuery(env, `
    SELECT
      blob2 AS service,
      blob3 AS environment,
      SUM(_sample_interval * double6) / 1000000.0 AS estimated_usd,
      SUM(_sample_interval) AS total_requests,
      AVG(double3) AS avg_kv_reads,
      AVG(double4) AS avg_kv_writes
    FROM COST_AE
    WHERE timestamp >= toStartOfMonth(now())
      AND blob1 = '${team}'
    GROUP BY service, environment
    ORDER BY estimated_usd DESC
  `);
}

/** Hourly cost trend for anomaly detection */
export async function hourlyCostTrend(env: Env, team: string, days: number = 7): Promise<any> {
  return runQuery(env, `
    SELECT
      toStartOfHour(timestamp) AS hour,
      blob1 AS team,
      SUM(_sample_interval * double6) / 1000000.0 AS estimated_usd,
      SUM(_sample_interval) AS requests
    FROM COST_AE
    WHERE timestamp >= now() - INTERVAL '${days}' DAY
      AND blob1 = '${team}'
    GROUP BY hour, team
    ORDER BY hour ASC
  `);
}
```

### Budget alert cron Worker

```typescript
// src/alerts.ts
import type { Env } from "./types";
import { costByTeam } from "./queries";

interface BudgetConfig {
  team: string;
  monthlyBudgetUsd: number;
  alertThresholdPct: number; // e.g. 0.8 = alert at 80% of budget
}

const BUDGETS: BudgetConfig[] = [
  { team: "platform", monthlyBudgetUsd: 500, alertThresholdPct: 0.8 },
  { team: "search",   monthlyBudgetUsd: 300, alertThresholdPct: 0.8 },
  { team: "ml",       monthlyBudgetUsd: 800, alertThresholdPct: 0.9 },
];

interface AnomalyResult {
  team: string;
  currentHourlyCost: number;
  baselineHourlyCost: number;
  spikeMultiple: number;
}

async function checkAnomalies(env: Env): Promise<AnomalyResult[]> {
  const { costByTeam: _unused, hourlyCostTrend } = await import("./queries");
  const anomalies: AnomalyResult[] = [];

  for (const budget of BUDGETS) {
    const trend = await hourlyCostTrend(env, budget.team, 7);
    const rows: any[] = trend?.data ?? [];
    if (rows.length < 25) continue; // need at least 25 hours of history

    // Last hour vs 7-day average (excluding last 2 hours)
    const historicalRows = rows.slice(0, -2);
    const baseline =
      historicalRows.reduce((s: number, r: any) => s + Number(r.estimated_usd), 0) /
      historicalRows.length;
    const current = Number(rows[rows.length - 1]?.estimated_usd ?? 0);

    if (baseline > 0 && current > baseline * 3) {
      anomalies.push({
        team: budget.team,
        currentHourlyCost: current,
        baselineHourlyCost: baseline,
        spikeMultiple: current / baseline,
      });
    }
  }
  return anomalies;
}

async function sendAlert(env: Env, message: string): Promise<void> {
  await fetch(env.ALERT_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: message }),
  });
}

export async function runBudgetCheck(env: Env): Promise<void> {
  const costs = await costByTeam(env);
  const rows: any[] = costs?.data ?? [];

  const now = new Date();
  const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const dayOfMonth = now.getDate();
  const monthFraction = dayOfMonth / daysInMonth;

  for (const budget of BUDGETS) {
    const row = rows.find((r: any) => r.team === budget.team);
    const spent = Number(row?.estimated_usd ?? 0);
    const projected = monthFraction > 0 ? spent / monthFraction : 0;

    if (spent >= budget.monthlyBudgetUsd * budget.alertThresholdPct) {
      await sendAlert(
        env,
        `[COST ALERT] Team *${budget.team}* has spent $${spent.toFixed(2)} ` +
        `(projected $${projected.toFixed(2)}) against a $${budget.monthlyBudgetUsd} monthly budget ` +
        `(${Math.round((spent / budget.monthlyBudgetUsd) * 100)}% used).`
      );
    }
  }

  const anomalies = await checkAnomalies(env);
  for (const a of anomalies) {
    await sendAlert(
      env,
      `[COST ANOMALY] Team *${a.team}* hourly cost spiked ${a.spikeMultiple.toFixed(1)}x ` +
      `($${a.currentHourlyCost.toFixed(4)}/hr vs baseline $${a.baselineHourlyCost.toFixed(4)}/hr).`
    );
  }
}
```

### wrangler.toml

```toml
name = "example project-cost-tracker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "COST_AE"
dataset = "cost_attribution"

[[kv_namespaces]]
binding = "COST_KV"
id = "<cost_kv_namespace_id>"

[vars]
TEAM_TAG = "platform"
SERVICE_TAG = "example project-api"
ENVIRONMENT = "production"

[triggers]
crons = ["0 * * * *"]  # budget check every hour
```

## Implementation Details

### Analytics Engine data point schema

The blobs and doubles arrays are positional. Document the schema and never reorder indices without creating a new dataset:

| Index | Type   | Field              |
|-------|--------|--------------------|
| blob1 | string | team               |
| blob2 | string | service            |
| blob3 | string | environment        |
| blob4 | string | version            |
| blob5 | string | http_method        |
| blob6 | string | path               |
| blob7 | string | country            |
| double1 | float | wall_time_ms       |
| double2 | float | cpu_time_ms        |
| double3 | float | kv_reads           |
| double4 | float | kv_writes          |
| double5 | float | subrequests        |
| double6 | float | estimated_usd_micros |

### _sample_interval in queries

Analytics Engine samples high-volume datasets. Always multiply your metric by `_sample_interval` in SUM aggregations to get accurate totals:

```sql
SUM(_sample_interval * double6) / 1000000.0 AS estimated_usd
-- NOT: SUM(double6) / 1000000.0  -- undercounts when sampled
```

## Anti-patterns

- **Blocking the response on cost ingestion** — always use `ctx.waitUntil()` for `writeDataPoint`. It is synchronous from the AE perspective but must not block the response.
- **Using a single `indexes` value for all teams** — AE indexes enable fast single-dimension scans. Set `indexes: [tag.team]` so team-scoped queries are efficient.
- **Computing cost in a reporting Worker on every dashboard request** — AE queries can be slow (1–5 s). Cache query results in KV with a 15-minute TTL for dashboard endpoints.
- **Querying AE from the hot path** — AE is a write-only API from the Worker runtime. Reads go through the REST `/sql` endpoint from a separate reporting Worker or external service.
- **Using wall time as a CPU time proxy in billing comparisons** — wall time includes I/O wait (KV reads, subrequests). CPU time (available via `performance.now()` around CPU-bound sections) is what Cloudflare bills against the CPU-time limit.

## Gotchas

- Analytics Engine datasets are created implicitly on first write. The dataset name in `wrangler.toml` must match the dataset name in SQL queries exactly.
- AE data has a ~5-minute ingestion delay before it appears in queries. Do not build real-time dashboards expecting sub-minute freshness.
- The AE SQL API returns an HTTP 200 even for queries with errors; check the `errors` field in the JSON response.
- `writeDataPoint` silently drops data points that exceed the size limit (20 blobs, 20 doubles, 1 index). Keep the schema within these limits.
- AE data retention is 31 days on the current plan. For longer retention, export daily rollups to D1 or R2 using a cron Worker.

## Verification

```bash
# Send a test request to generate a data point
curl https://example project-api.example.com/v1/health

# Wait ~5 minutes for AE ingestion, then query
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: text/plain" \
  --data "SELECT blob1 AS team, COUNT(*) AS requests, SUM(_sample_interval * double6) / 1000000.0 AS usd FROM cost_attribution WHERE timestamp >= now() - INTERVAL '1' HOUR GROUP BY team" \
  | jq .

# Trigger budget check manually
wrangler triggers fire example project-cost-tracker

# Check KV for any cached budget state
wrangler kv key list --namespace-id=<cost_kv_id>
```

## Related

- `documentation/categories/infra/workers-terraform-cloudflare-provider.md`
- `documentation/categories/infra/workers-secrets-rotation-kv-vault.md`
- `documentation/categories/infra/workers-multi-region-failover-routing.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
- https://developers.cloudflare.com/workers/platform/pricing/
