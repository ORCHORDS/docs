# Per-Request Cost Attribution Tracking with Workers + Analytics Engine

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You are running Workers-based services at scale and see unexpectedly high Cloudflare bills but cannot attribute cost to specific endpoints, users, or features. You need per-request cost breakdown covering Workers CPU time, D1 queries, KV operations, and Queues messages — with a daily budget alert and an Analytics Engine query for per-endpoint cost.

## Context

Cloudflare pricing model (as of 2026):
- **Workers**: $0.30 per million CPU milliseconds (Paid plan, beyond free tier)
- **D1**: $0.001 per 1,000 rows read; $0.001 per 1,000 rows written
- **KV**: $0.50 per million reads; $5.00 per million writes
- **Queues**: $0.40 per million operations (send + receive)

Each Worker invocation exposes `ctx.waitUntil` (non-blocking) for cost telemetry writes. A middleware intercepts request start/end, collects per-resource counters via a context object, converts to USD, and writes a single data point to Analytics Engine. A cron Worker checks daily spend against budget and pages if over threshold.

## Solution

### 1. Cost constants and conversion utilities

```typescript
// src/lib/cost.ts

// All costs in USD per unit
export const PRICING = {
  // Workers: $0.30 per 1M CPU-ms = $3e-7 per CPU-ms
  workerCpuMsPerUsd: 1_000_000 / 0.30,
  workerCpuUsdPerMs: 0.30 / 1_000_000,

  // D1: $0.001 per 1k rows read = $1e-6 per row read
  d1RowReadUsdPer1k: 0.001,
  d1RowReadUsdPer1: 0.000_001,

  // D1: $0.001 per 1k rows written
  d1RowWriteUsdPer1: 0.000_001,

  // KV: $0.50 per 1M reads = $5e-7 per read
  kvReadUsdPer1: 0.50 / 1_000_000,

  // KV: $5.00 per 1M writes = $5e-6 per write
  kvWriteUsdPer1: 5.00 / 1_000_000,

  // Queues: $0.40 per 1M operations = $4e-7 per op
  queueOpUsdPer1: 0.40 / 1_000_000,
} as const;

export interface RequestCostBreakdown {
  cpuTimeMs: number;
  d1RowsRead: number;
  d1RowsWritten: number;
  kvReads: number;
  kvWrites: number;
  queueOps: number;
}

export function calculateCost(b: RequestCostBreakdown): {
  workerUsd: number;
  d1Usd: number;
  kvUsd: number;
  queuesUsd: number;
  totalUsd: number;
} {
  const workerUsd = b.cpuTimeMs * PRICING.workerCpuUsdPerMs;
  const d1Usd =
    b.d1RowsRead * PRICING.d1RowReadUsdPer1 +
    b.d1RowsWritten * PRICING.d1RowWriteUsdPer1;
  const kvUsd =
    b.kvReads * PRICING.kvReadUsdPer1 +
    b.kvWrites * PRICING.kvWriteUsdPer1;
  const queuesUsd = b.queueOps * PRICING.queueOpUsdPer1;
  return {
    workerUsd,
    d1Usd,
    kvUsd,
    queuesUsd,
    totalUsd: workerUsd + d1Usd + kvUsd + queuesUsd,
  };
}
```

### 2. Request cost context — tracking counters

```typescript
// src/lib/cost-context.ts
export class CostContext {
  d1RowsRead = 0;
  d1RowsWritten = 0;
  kvReads = 0;
  kvWrites = 0;
  queueOps = 0;

  trackD1Read(rowCount: number) { this.d1RowsRead += rowCount; }
  trackD1Write(rowCount: number) { this.d1RowsWritten += rowCount; }
  trackKVRead(count = 1) { this.kvReads += count; }
  trackKVWrite(count = 1) { this.kvWrites += count; }
  trackQueueOp(count = 1) { this.queueOps += count; }
}

// Attach to Hono context via middleware
declare module 'hono' {
  interface ContextVariableMap {
    cost: CostContext;
  }
}
```

### 3. Cost tracking middleware

```typescript
// src/middleware/cost-tracking.ts
import { MiddlewareHandler } from 'hono';
import { CostContext } from '../lib/cost-context';
import { calculateCost, RequestCostBreakdown } from '../lib/cost';

interface CostEnv {
  COST_ANALYTICS: AnalyticsEngineDataset;
}

export const costTrackingMiddleware: MiddlewareHandler<{ Bindings: CostEnv }> = async (c, next) => {
  const costCtx = new CostContext();
  c.set('cost', costCtx);

  const startTime = Date.now();
  await next();
  const wallTimeMs = Date.now() - startTime;

  // CPU time is not directly available mid-request; use wall time as proxy.
  // For accurate CPU time, read from the tail Worker's cpuTime field instead.
  const breakdown: RequestCostBreakdown = {
    cpuTimeMs: wallTimeMs,  // replace with actual CPU time from tail if available
    d1RowsRead: costCtx.d1RowsRead,
    d1RowsWritten: costCtx.d1RowsWritten,
    kvReads: costCtx.kvReads,
    kvWrites: costCtx.kvWrites,
    queueOps: costCtx.queueOps,
  };

  const cost = calculateCost(breakdown);
  const url = new URL(c.req.url);

  // Write cost data point to Analytics Engine (non-blocking)
  c.executionCtx.waitUntil(
    Promise.resolve().then(() => {
      c.env.COST_ANALYTICS.writeDataPoint({
        indexes: [
          url.pathname,                    // index1: endpoint path
          c.req.method,                    // index2: HTTP method
          String(c.res.status),           // index3: response status
        ],
        doubles: [
          cost.totalUsd,                   // double1: total request cost USD
          cost.workerUsd,                  // double2: worker CPU cost
          cost.d1Usd,                      // double3: D1 cost
          cost.kvUsd,                      // double4: KV cost
          cost.queuesUsd,                  // double5: Queues cost
          breakdown.cpuTimeMs,             // double6: wall/cpu time ms
          breakdown.d1RowsRead,            // double7: D1 rows read
          breakdown.d1RowsWritten,         // double8: D1 rows written
          breakdown.kvReads,               // double9: KV reads
          breakdown.kvWrites,              // double10: KV writes
        ],
      });
    })
  );
};
```

### 4. Using the cost context in handlers

```typescript
// src/workers/api-handler.ts
import { Hono } from 'hono';
import { costTrackingMiddleware } from '../middleware/cost-tracking';

const app = new Hono<{ Bindings: { DB: D1Database; CACHE: KVNamespace; COST_ANALYTICS: AnalyticsEngineDataset } }>();

app.use('*', costTrackingMiddleware);

app.get('/api/users/:id', async (c) => {
  const cost = c.get('cost');

  // Track KV read
  const cached = await c.env.CACHE.get(`user:${c.req.param('id')}`);
  cost.trackKVRead();

  if (cached) return c.json(JSON.parse(cached));

  // Track D1 read
  const result = await c.env.DB.prepare('SELECT * FROM users WHERE id = ?')
    .bind(c.req.param('id'))
    .all();
  cost.trackD1Read(result.results.length);

  const user = result.results[0];
  if (!user) return c.json({ error: 'not found' }, 404);

  // Track KV write (cache set)
  await c.env.CACHE.put(`user:${c.req.param('id')}`, JSON.stringify(user), { expirationTtl: 300 });
  cost.trackKVWrite();

  return c.json(user);
});

export default app;
```

### 5. Per-endpoint cost SQL query

```sql
-- Analytics Engine SQL — top 10 most expensive endpoints (last 24h)
SELECT
  index1                        AS endpoint,
  index2                        AS method,
  COUNT()                       AS request_count,
  SUM(double1)                  AS total_cost_usd,
  AVG(double1)                  AS avg_cost_per_req_usd,
  MAX(double1)                  AS max_cost_per_req_usd,
  SUM(double3)                  AS total_d1_cost_usd,
  SUM(double4)                  AS total_kv_cost_usd,
  SUM(double7)                  AS total_d1_rows_read,
  SUM(double9)                  AS total_kv_reads
FROM COST_ANALYTICS
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY endpoint, method
ORDER BY total_cost_usd DESC
LIMIT 10
```

### 6. Daily cost budget alert Worker

```typescript
// src/workers/cost-budget-alert.ts
interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  DAILY_BUDGET_USD: string;   // e.g. "5.00"
  ALERT_WEBHOOK_URL: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const budget = parseFloat(env.DAILY_BUDGET_USD);
    const today = new Date().toISOString().slice(0, 10);

    const sql = `
      SELECT SUM(double1) AS daily_total_usd
      FROM COST_ANALYTICS
      WHERE timestamp >= '${today}T00:00:00Z'
    `;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: sql }),
      }
    );

    if (!res.ok) {
      console.error('AE query failed', await res.text());
      return;
    }

    const json = (await res.json()) as { data: Array<{ daily_total_usd: number }> };
    const dailyTotal = json.data[0]?.daily_total_usd ?? 0;
    const pct = (dailyTotal / budget) * 100;

    console.log(`Daily cost: $${dailyTotal.toFixed(6)} / $${budget} (${pct.toFixed(1)}%)`);

    if (dailyTotal >= budget) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `COST ALERT: Daily spend $${dailyTotal.toFixed(4)} has reached/exceeded budget $${budget} (${pct.toFixed(1)}%)`,
        }),
      });
    } else if (pct >= 80) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `COST WARNING: Daily spend $${dailyTotal.toFixed(4)} is at ${pct.toFixed(1)}% of budget $${budget}`,
        }),
      });
    }
  },
};
```

## Implementation Details

- **CPU time accuracy**: The `cpuTime` field is available in the tail Worker's `TraceItem`, not in the request handler itself. For accurate CPU-time cost, compute cost in a tail Worker that receives `cpuTime` as a number of milliseconds, then write the cost data point there instead of in the middleware.
- **Analytics Engine doubles**: AE supports up to 20 `doubles` per data point. Allocate them consistently across all your Workers to enable cross-service cost queries.
- **D1 row count**: `result.meta.rows_read` and `result.meta.rows_written` are available on D1 results in addition to `result.results.length`. Use `meta` fields for accurate billing-equivalent row counts.
- **Budget granularity**: The daily budget alert runs hourly. At 80% threshold it warns; at 100% it alerts. Adjust thresholds and schedule for tighter control.

## Anti-patterns

- **Using wall time for CPU cost**: Wall time includes I/O wait, which is not billed as CPU time. Use `cpuTime` from the tail Worker for accurate Worker CPU cost attribution.
- **Aggregating cost in D1 instead of AE**: AE is designed for high-write-volume telemetry. Writing a row to D1 per request defeats the purpose and adds D1 cost on top.
- **Tracking cost inside Queue consumer Workers**: Queue consumers are billed per invocation, not per message. Adjust cost attribution logic for consumer Workers.
- **Not tracking D1 `meta.rows_read`**: A single D1 query can read thousands of rows due to a missing index. Track `meta.rows_read` explicitly, not just result count.

## Gotchas

- Analytics Engine `writeDataPoint` is fire-and-forget and non-blocking. Errors are silently swallowed. Wrap in try/catch in `waitUntil` if you want error logging.
- KV read costs apply even on cache miss (the read is billed whether the key exists or not).
- The free tier for Workers includes 10M requests and 30M CPU-ms per day. Costs above apply only to usage beyond the free tier. Adjust your `PRICING` constants if you are on a specific plan with different rates.
- D1 pricing is per million rows, not per query. A full-table scan on a 10M row table costs 10x a query returning 1M rows.
- `double1` through `double20` are positional, not named, in Analytics Engine. Document your schema carefully to avoid mixing up cost components across different Worker versions.

## Verification

1. Make 10 requests to `/api/users/:id` mixing cache hits and misses.
2. Query AE: `SELECT SUM(double1) AS total_usd, AVG(double9) AS avg_kv_reads FROM COST_ANALYTICS WHERE timestamp > NOW() - INTERVAL '5' MINUTE`.
3. Set `DAILY_BUDGET_USD=0.000001` (sub-cent) and trigger the cron to confirm the alert fires.
4. Compare KV write cost estimate against Cloudflare dashboard usage numbers at end of month.
5. Run `wrangler tail` and observe the cost data point log for each request.

## Related

- `workers-metric-aggregation-cron-d1` — roll up hourly/daily cost totals into D1 for long-term retention
- `workers-structured-logging-analytics-engine` — base Analytics Engine write pattern
- `tail-worker-request-sampling` — tail Worker that captures `cpuTime` per request
- `workers-error-budget-tracking-d1` — combine cost tracking with SLO error budget

## Sources

- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/kv/platform/pricing/
- https://developers.cloudflare.com/queues/platform/pricing/
- https://developers.cloudflare.com/analytics/analytics-engine/get-started/#write-data-points-from-a-worker
- https://developers.cloudflare.com/workers/observability/tail-workers/
