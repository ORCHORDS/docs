# Cloudflare Workers Cost Modeling with D1 and Analytics Engine

- Date: 2026-08-22
- Author: example.com
- Status: production

## Forecasting Workers Spend Before the Invoice Arrives

Cloudflare publishes per-request and per-CPU-millisecond pricing for Workers, per-row pricing for D1, and per-read pricing for KV—but none of those metrics roll up automatically into a per-service cost line. By the time the monthly invoice arrives you know the total, not which Worker drove the spike. The solution is a lightweight cost-modeling pipeline: each Worker emits per-request telemetry to Workers Analytics Engine (WAE), a scheduled aggregation Worker rolls that up into D1 daily cost snapshots, and a threshold check fires an alert if the rolling 7-day projection exceeds a budget.

D1 is used as the persistent model store because it is already in the stack and its SQL interface makes ad-hoc cost queries trivial. WAE is used as the ingestion layer because it can accept millions of data points per day without counting against D1 row limits, and its aggregation SQL (`SELECT quantilesMerge`, `sumMerge`) compresses the raw stream efficiently. The pattern is entirely serverless—no external metrics infrastructure required.

Costs covered: Workers requests (free tier 10 M/month, then $0.30/M), Workers CPU-ms (free tier 30 M CPU-ms/day on Paid, then $0.02/M), D1 read rows ($0.001/M), D1 write rows ($1.00/M), KV reads ($0.50/M), R2 Class A ops ($4.50/M).

## Context

- Workers Paid plan required for WAE and scheduled Workers
- D1 database `cost_model` pre-created (`wrangler d1 create cost-model`)
- WAE dataset `workers_telemetry` created via API or wrangler
- Budget values stored in a KV namespace `BUDGETS`

## D1 Schema

```sql
-- Run via wrangler d1 execute cost-model --file=schema.sql
CREATE TABLE IF NOT EXISTS daily_cost_snapshot (
  snapshot_date TEXT NOT NULL,      -- ISO date YYYY-MM-DD
  service       TEXT NOT NULL,      -- Worker script name
  requests      INTEGER NOT NULL DEFAULT 0,
  cpu_ms        REAL    NOT NULL DEFAULT 0,
  kv_reads      INTEGER NOT NULL DEFAULT 0,
  d1_reads      INTEGER NOT NULL DEFAULT 0,
  d1_writes     INTEGER NOT NULL DEFAULT 0,
  estimated_usd REAL    NOT NULL DEFAULT 0,
  PRIMARY KEY (snapshot_date, service)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_service ON daily_cost_snapshot(service, snapshot_date);
```

## Telemetry Emission in Each Worker

```typescript
// src/telemetry.ts — imported by every Worker
export interface WorkerMetrics {
  cpuMs: number;
  kvReads: number;
  d1Reads: number;
  d1Writes: number;
}

export function emitTelemetry(
  env: { TELEMETRY: AnalyticsEngineDataset },
  service: string,
  metrics: WorkerMetrics
): void {
  env.TELEMETRY.writeDataPoint({
    blobs: [service],
    doubles: [
      1,                  // request count
      metrics.cpuMs,
      metrics.kvReads,
      metrics.d1Reads,
      metrics.d1Writes,
    ],
    indexes: [service],
  });
}

// src/worker.ts — usage
export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    let kvReads = 0, d1Reads = 0, d1Writes = 0;

    // ... business logic, increment counters ...

    ctx.waitUntil(
      Promise.resolve().then(() =>
        emitTelemetry(env, "api-worker", {
          cpuMs: Date.now() - start,
          kvReads,
          d1Reads,
          d1Writes,
        })
      )
    );
    return new Response("ok");
  },
};
```

## Scheduled Aggregation Worker

```typescript
// src/aggregator.ts — runs every 24 h via cron trigger "0 1 * * *"
const PRICING = {
  requestsPer1M:  0.30,   // USD, above free tier
  cpuMsPer1M:     0.02,
  kvReadsPer1M:   0.50,
  d1ReadsPer1M:   0.001,
  d1WritesPer1M:  1.00,
};

function estimateCost(row: {
  requests: number; cpu_ms: number; kv_reads: number;
  d1_reads: number; d1_writes: number;
}): number {
  return (
    (row.requests  / 1_000_000) * PRICING.requestsPer1M +
    (row.cpu_ms    / 1_000_000) * PRICING.cpuMsPer1M    +
    (row.kv_reads  / 1_000_000) * PRICING.kvReadsPer1M  +
    (row.d1_reads  / 1_000_000) * PRICING.d1ReadsPer1M  +
    (row.d1_writes / 1_000_000) * PRICING.d1WritesPer1M
  );
}

export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    const yesterday = new Date(Date.now() - 86_400_000)
      .toISOString().slice(0, 10);

    // Pull yesterday's rollup from Analytics Engine SQL API
    const waeResp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: `
            SELECT
              blob1                  AS service,
              sum(double1)           AS requests,
              sum(double2)           AS cpu_ms,
              sum(double3)           AS kv_reads,
              sum(double4)           AS d1_reads,
              sum(double5)           AS d1_writes
            FROM workers_telemetry
            WHERE timestamp >= toDateTime('${yesterday} 00:00:00')
              AND timestamp <  toDateTime('${yesterday} 23:59:59')
            GROUP BY blob1
          `,
        }),
      }
    );

    const { data } = (await waeResp.json()) as { data: any[] };

    for (const row of data) {
      const usd = estimateCost(row);
      await env.DB.prepare(
        `INSERT OR REPLACE INTO daily_cost_snapshot
           (snapshot_date, service, requests, cpu_ms, kv_reads, d1_reads, d1_writes, estimated_usd)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        yesterday, row.service,
        row.requests, row.cpu_ms, row.kv_reads, row.d1_reads, row.d1_writes,
        usd
      ).run();

      // Alert if 7-day rolling projection exceeds budget
      const budgetStr = await env.BUDGETS.get(`budget:${row.service}`);
      if (budgetStr) {
        const budget = parseFloat(budgetStr);
        const { results } = await env.DB.prepare(
          `SELECT SUM(estimated_usd) AS week_usd
           FROM daily_cost_snapshot
           WHERE service = ? AND snapshot_date >= date(?, '-6 days')`
        ).bind(row.service, yesterday).all();
        const weekUsd = (results[0] as any)?.week_usd ?? 0;
        const projectedMonthly = (weekUsd / 7) * 30;
        if (projectedMonthly > budget) {
          await fetch(env.ALERT_WEBHOOK, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              text: `Cost alert: ${row.service} projected $${projectedMonthly.toFixed(2)}/mo (budget $${budget})`,
            }),
          });
        }
      }
    }
  },
};
```

## Anti-patterns

- Polling D1 directly from every request to track cost—use `ctx.waitUntil` + WAE to keep the hot path clean.
- Storing raw per-request rows in D1—WAE compresses millions of events into aggregate SQL; D1 is for daily snapshots only.
- Hard-coding pricing constants in multiple Workers—centralise in a shared KV key so a Cloudflare price change requires a single KV update.
- Setting per-service budgets without accounting for the free-tier offset—the free 10 M requests/month means the first Worker is cheaper than later ones.

## Gotchas

- WAE data has ~2-minute ingestion lag; the aggregation cron should run at `0 1 * * *` (01:00 UTC) to ensure yesterday's data is fully settled.
- Analytics Engine SQL API returns results as JSON with string-typed numbers—parse with `parseFloat` before arithmetic.
- D1's `INSERT OR REPLACE` deletes the old row and inserts a new one, resetting the rowid; use it only where the primary key is stable (date + service).
- The WAE free tier is 100 K data points/day per account, not per Worker. On high-traffic accounts, switch to sampled telemetry (1-in-N) and scale the counters.

## Verification

```bash
# Check D1 snapshots
wrangler d1 execute cost-model \
  --command "SELECT * FROM daily_cost_snapshot ORDER BY snapshot_date DESC LIMIT 10"

# Manually trigger aggregation Worker
wrangler dev src/aggregator.ts --trigger

# Query WAE directly
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1, count() FROM workers_telemetry GROUP BY blob1 LIMIT 20"}'
```

## Related

- `/documentation/docs/policies/infra/cloudflare-workers-cost-optimization-scale.md`
- `/documentation/docs/policies/infra/workers-analytics-billing-monitoring.md`
- `/documentation/docs/policies/infra/cloudflare-workers-limits-resource-planning.md`
- `/documentation/docs/policies/infra/keda-cloudflare-queue-consumers.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
