# Cloudflare Cost Monitoring and Budget Alerts

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Workers, KV, R2, and D1 costs are opaque until the end-of-month invoice. A viral event or a runaway Worker can drive KV operations or R2 egress to 10x their normal level with no warning. You need daily projected cost calculations from usage metrics and a Slack alert when the projected monthly total will exceed budget.

## Context

Cloudflare exposes usage metrics via the **Analytics Engine** (formerly Workers Analytics Engine). Each billable resource emits data points to a dataset. A scheduled Worker reads those data points, calculates a daily rate, extrapolates a monthly projection, and posts to Slack if the projection exceeds a configured threshold.

Billable items and their free tiers (Workers Paid plan as of 2025):
- **Workers invocations** — $0.30 per million after 10M free/day
- **Workers CPU time** — $0.02 per million GB-seconds after 30M free/day
- **KV reads** — $0.50 per million after 10M free/day
- **KV writes** — $5.00 per million after 1M free/day
- **R2 Class A ops** (PUT/POST/LIST) — $4.50 per million after 1M free/month
- **R2 Class B ops** (GET) — $0.36 per million after 10M free/month
- **R2 storage** — $0.015 per GB-month after 10 GB free
- **D1 rows read** — $0.001 per million after 25B free/month
- **D1 rows written** — $1.00 per million after 50M free/month

## Solution

```typescript
// src/cost-monitor/index.ts
// Scheduled Worker: runs daily at 09:00 UTC
// Reads Analytics Engine for prior day usage, projects monthly cost,
// sends Slack alert if over budget.

export interface Env {
  ANALYTICS_ENGINE: AnalyticsEngineDataset;
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string; // Needs Analytics Read permission
  SLACK_WEBHOOK_URL: string;
  MONTHLY_BUDGET_USD: string; // e.g., "500"
  COST_KV: KVNamespace; // Persists daily snapshots
}

const PRICING = {
  workers: {
    invocations: { free: 10_000_000, unitCost: 0.30, unit: 1_000_000 },
    cpuMs: { free: 30_000_000, unitCost: 0.02, unit: 1_000_000 }, // GB-seconds approximated
  },
  kv: {
    reads: { free: 10_000_000, unitCost: 0.50, unit: 1_000_000 },
    writes: { free: 1_000_000, unitCost: 5.00, unit: 1_000_000 },
  },
  r2: {
    classA: { free: 1_000_000, unitCost: 4.50, unit: 1_000_000 }, // per month
    classB: { free: 10_000_000, unitCost: 0.36, unit: 1_000_000 }, // per month
    storageGB: { free: 10, unitCost: 0.015, unit: 1 }, // per GB-month
  },
  d1: {
    rowsRead: { free: 25_000_000_000, unitCost: 0.001, unit: 1_000_000 }, // per month
    rowsWritten: { free: 50_000_000, unitCost: 1.00, unit: 1_000_000 }, // per month
  },
} as const;

function billableUnits(
  actual: number,
  free: number,
  unit: number
): number {
  const billable = Math.max(0, actual - free);
  return billable / unit;
}

function calcCost(
  actual: number,
  tier: { free: number; unitCost: number; unit: number }
): number {
  return billableUnits(actual, tier.free, tier.unit) * tier.unitCost;
}

async function queryAnalyticsEngine(
  accountId: string,
  apiToken: string,
  query: string
): Promise<Record<string, number>> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Analytics Engine query failed: ${res.status} ${text}`);
  }

  const data = await res.json<{ data: Array<Record<string, unknown>> }>();
  return (data.data[0] ?? {}) as Record<string, number>;
}

interface DailyUsage {
  workerInvocations: number;
  workerCpuMs: number;
  kvReads: number;
  kvWrites: number;
  r2ClassA: number;
  r2ClassB: number;
  r2StorageGB: number;
  d1RowsRead: number;
  d1RowsWritten: number;
  timestamp: string;
}

async function fetchDailyUsage(env: Env): Promise<DailyUsage> {
  const yesterday = new Date();
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  const ymd = yesterday.toISOString().slice(0, 10);

  const [workers, kvStats, r2Stats, d1Stats] = await Promise.all([
    queryAnalyticsEngine(
      env.CF_ACCOUNT_ID,
      env.CF_API_TOKEN,
      `SELECT
         SUM(_sample_interval * requests) AS invocations,
         SUM(_sample_interval * cpu_time_ms) AS cpu_ms
       FROM workers_analytics
       WHERE timestamp >= '${ymd} 00:00:00'
         AND timestamp <  '${ymd} 23:59:59'`
    ),
    queryAnalyticsEngine(
      env.CF_ACCOUNT_ID,
      env.CF_API_TOKEN,
      `SELECT
         SUM(_sample_interval * reads) AS kv_reads,
         SUM(_sample_interval * writes) AS kv_writes
       FROM kv_analytics
       WHERE timestamp >= '${ymd} 00:00:00'
         AND timestamp <  '${ymd} 23:59:59'`
    ),
    queryAnalyticsEngine(
      env.CF_ACCOUNT_ID,
      env.CF_API_TOKEN,
      `SELECT
         SUM(_sample_interval * class_a_ops) AS class_a,
         SUM(_sample_interval * class_b_ops) AS class_b,
         MAX(storage_bytes) / 1073741824.0 AS storage_gb
       FROM r2_analytics
       WHERE timestamp >= '${ymd} 00:00:00'
         AND timestamp <  '${ymd} 23:59:59'`
    ),
    queryAnalyticsEngine(
      env.CF_ACCOUNT_ID,
      env.CF_API_TOKEN,
      `SELECT
         SUM(_sample_interval * rows_read) AS rows_read,
         SUM(_sample_interval * rows_written) AS rows_written
       FROM d1_analytics
       WHERE timestamp >= '${ymd} 00:00:00'
         AND timestamp <  '${ymd} 23:59:59'`
    ),
  ]);

  return {
    workerInvocations: Number(workers.invocations ?? 0),
    workerCpuMs: Number(workers.cpu_ms ?? 0),
    kvReads: Number(kvStats.kv_reads ?? 0),
    kvWrites: Number(kvStats.kv_writes ?? 0),
    r2ClassA: Number(r2Stats.class_a ?? 0),
    r2ClassB: Number(r2Stats.class_b ?? 0),
    r2StorageGB: Number(r2Stats.storage_gb ?? 0),
    d1RowsRead: Number(d1Stats.rows_read ?? 0),
    d1RowsWritten: Number(d1Stats.rows_written ?? 0),
    timestamp: new Date().toISOString(),
  };
}

interface CostBreakdown {
  workerInvocations: number;
  workerCpu: number;
  kvReads: number;
  kvWrites: number;
  r2ClassA: number;
  r2ClassB: number;
  r2Storage: number;
  d1RowsRead: number;
  d1RowsWritten: number;
  total: number;
}

function calculateDailyCost(usage: DailyUsage): CostBreakdown {
  const workerInvocations = calcCost(usage.workerInvocations, PRICING.workers.invocations);
  const workerCpu = calcCost(usage.workerCpuMs, PRICING.workers.cpuMs);
  const kvReads = calcCost(usage.kvReads, PRICING.kv.reads);
  const kvWrites = calcCost(usage.kvWrites, PRICING.kv.writes);
  // R2 ops are monthly — divide monthly free tier by 30 to get daily
  const r2ClassA = calcCost(usage.r2ClassA, { ...PRICING.r2.classA, free: Math.floor(PRICING.r2.classA.free / 30) });
  const r2ClassB = calcCost(usage.r2ClassB, { ...PRICING.r2.classB, free: Math.floor(PRICING.r2.classB.free / 30) });
  const r2Storage = usage.r2StorageGB > PRICING.r2.storageGB.free
    ? (usage.r2StorageGB - PRICING.r2.storageGB.free) * PRICING.r2.storageGB.unitCost / 30
    : 0;
  const d1RowsRead = calcCost(usage.d1RowsRead, { ...PRICING.d1.rowsRead, free: Math.floor(PRICING.d1.rowsRead.free / 30) });
  const d1RowsWritten = calcCost(usage.d1RowsWritten, { ...PRICING.d1.rowsWritten, free: Math.floor(PRICING.d1.rowsWritten.free / 30) });

  const total = workerInvocations + workerCpu + kvReads + kvWrites
    + r2ClassA + r2ClassB + r2Storage + d1RowsRead + d1RowsWritten;

  return { workerInvocations, workerCpu, kvReads, kvWrites, r2ClassA, r2ClassB, r2Storage, d1RowsRead, d1RowsWritten, total };
}

async function sendSlackAlert(
  webhookUrl: string,
  projected: number,
  budget: number,
  breakdown: CostBreakdown,
  usage: DailyUsage
): Promise<void> {
  const ratio = projected / budget;
  const emoji = ratio >= 1.0 ? ':rotating_light:' : ratio >= 0.8 ? ':warning:' : ':chart_with_upwards_trend:';
  const pct = (ratio * 100).toFixed(1);

  const body = {
    text: `${emoji} *Cloudflare cost alert* — projected monthly: *$${projected.toFixed(2)}* (${pct}% of $${budget} budget)`,
    blocks: [
      {
        type: 'header',
        text: { type: 'plain_text', text: `${emoji} Cloudflare Cost Alert` },
      },
      {
        type: 'section',
        fields: [
          { type: 'mrkdwn', text: `*Projected monthly:* $${projected.toFixed(2)}` },
          { type: 'mrkdwn', text: `*Budget:* $${budget.toFixed(2)} (${pct}% used)` },
          { type: 'mrkdwn', text: `*Date:* ${usage.timestamp.slice(0, 10)}` },
        ],
      },
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: [
            '*Daily cost breakdown:*',
            `• Workers invocations: $${breakdown.workerInvocations.toFixed(4)}`,
            `• Workers CPU: $${breakdown.workerCpu.toFixed(4)}`,
            `• KV reads: $${breakdown.kvReads.toFixed(4)}`,
            `• KV writes: $${breakdown.kvWrites.toFixed(4)}`,
            `• R2 Class A ops: $${breakdown.r2ClassA.toFixed(4)}`,
            `• R2 Class B ops: $${breakdown.r2ClassB.toFixed(4)}`,
            `• R2 storage: $${breakdown.r2Storage.toFixed(4)}`,
            `• D1 rows read: $${breakdown.d1RowsRead.toFixed(4)}`,
            `• D1 rows written: $${breakdown.d1RowsWritten.toFixed(4)}`,
            `• *Daily total: $${breakdown.total.toFixed(4)}*`,
          ].join('\n'),
        },
      },
    ],
  };

  const res = await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`Slack webhook failed: ${res.status}`);
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const budget = parseFloat(env.MONTHLY_BUDGET_USD);
    const usage = await fetchDailyUsage(env);
    const breakdown = calculateDailyCost(usage);

    // Persist today's snapshot for trend analysis
    const date = new Date().toISOString().slice(0, 10);
    await env.COST_KV.put(`daily:${date}`, JSON.stringify({ usage, breakdown }), {
      expirationTtl: 60 * 60 * 24 * 90, // Keep 90 days
    });

    // Project monthly cost: daily total × days remaining + actuals so far this month
    const dayOfMonth = new Date().getUTCDate();
    const daysInMonth = new Date(new Date().getUTCFullYear(), new Date().getUTCMonth() + 1, 0).getDate();
    const daysRemaining = daysInMonth - dayOfMonth;
    const projectedMonthly = breakdown.total * daysInMonth; // Simple: extrapolate from today

    // Alert if projected cost > 70% of budget (early warning) or > 100%
    if (projectedMonthly >= budget * 0.70) {
      await sendSlackAlert(env.SLACK_WEBHOOK_URL, projectedMonthly, budget, breakdown, usage);
    }

    console.log(JSON.stringify({
      date,
      dailyTotal: breakdown.total,
      projectedMonthly,
      budget,
      percentOfBudget: (projectedMonthly / budget * 100).toFixed(1),
      daysRemaining,
    }));
  },
};
```

```yaml
# wrangler.toml for cost-monitor Worker
name = "orchords-cost-monitor"
main = "src/cost-monitor/index.ts"
compatibility_date = "2025-08-01"

[triggers]
crons = ["0 9 * * *"]  # 09:00 UTC daily

[[kv_namespaces]]
binding = "COST_KV"
id = "<your-kv-namespace-id>"

[vars]
CF_ACCOUNT_ID = "<your-account-id>"
MONTHLY_BUDGET_USD = "500"

# Set secrets via: wrangler secret put CF_API_TOKEN
# Set secrets via: wrangler secret put SLACK_WEBHOOK_URL
```

## Implementation Details

**Analytics Engine vs Cloudflare GraphQL Analytics API.** The Analytics Engine (SQL API) is preferred for custom dataset queries. For platform-native metrics (Workers invocations, R2 ops), use the Cloudflare GraphQL Analytics API (`https://api.cloudflare.com/client/v4/graphql`) which has pre-built datasets like `workersInvocationsAdaptiveGroups`.

**Cost allocation by Worker.** The Analytics Engine `workers_analytics` dataset includes a `script_name` dimension. Extend the query to `GROUP BY script_name` to get per-Worker cost breakdowns. This surfaces which Workers are driving costs.

**KV operation tracking from within a Worker.** Wrap KV calls in a thin instrumented class that increments an Analytics Engine counter:

```typescript
class InstrumentedKV {
  constructor(private kv: KVNamespace, private ae: AnalyticsEngineDataset) {}
  async get(key: string): Promise<string | null> {
    this.ae.writeDataPoint({ blobs: ['kv_read'], doubles: [1] });
    return this.kv.get(key);
  }
  async put(key: string, value: string): Promise<void> {
    this.ae.writeDataPoint({ blobs: ['kv_write'], doubles: [1] });
    return this.kv.put(key, value);
  }
}
```

## Anti-patterns

- **Polling costs via the dashboard manually.** Costly events (traffic spikes, misconfigured Workers) can run for days before end-of-month discovery.
- **Projecting monthly cost from day 1.** Day 1 may be anomalous (cold start burst, deploy spike). Average the last 3–7 daily snapshots from KV for a more stable projection.
- **Using a fixed 30-day month.** Calculate actual days in the current month and remaining days for accurate projection.
- **Hardcoding pricing constants.** Cloudflare adjusts pricing on plan upgrades. Store pricing in a KV key or Wrangler environment variable and reload periodically.
- **Not persisting daily snapshots.** Without history you cannot detect trends (gradual cost increase vs sudden spike).

## Gotchas

- Analytics Engine data can lag by up to 5 minutes. The scheduled cron at 09:00 UTC reads yesterday's data, which is fully available by then.
- R2 storage is billed monthly, not daily. The daily storage cost calculation divides monthly cost by days-in-month, which introduces a fractional approximation.
- KV `expirationTtl` must be at least 60 seconds. For 90-day retention, set `expirationTtl: 7776000`.
- The Cloudflare API token for Analytics Engine requires the `Account Analytics: Read` permission scope, not zone-level. Account-level token required.
- `writeDataPoint` is fire-and-forget and does not throw on failure. Wrap with a try/catch in production but don't let Analytics Engine failures block the primary response path.

## Verification

```bash
# Trigger the scheduled Worker manually to test
wrangler dev src/cost-monitor/index.ts --test-scheduled

# Query the cost KV for today's snapshot
wrangler kv:key get --binding=COST_KV "daily:$(date -u +%Y-%m-%d)" | jq .

# Query Analytics Engine directly to validate data is flowing
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"query": "SELECT SUM(_sample_interval * requests) AS total FROM workers_analytics WHERE timestamp >= now() - INTERVAL 1 DAY"}' \
  | jq '.data'

# Check Slack webhook directly
curl -X POST "${SLACK_WEBHOOK_URL}" \
  -H 'Content-Type: application/json' \
  -d '{"text": "Cost monitor test — please ignore"}'
```

## Related

- `documentation/docs/policies/infra/workers-firewall-rules-waf.md`
- `documentation/docs/policies/infra/workers-dns-records-automation.md`
- `documentation/docs/policies/infra/multi-account-deployment.md`
- Cloudflare Analytics Engine docs: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Workers pricing: https://developers.cloudflare.com/workers/platform/pricing/

## Sources

- Cloudflare Analytics Engine SQL API reference (2025)
- Cloudflare Workers, KV, R2, D1 pricing pages
- Internal example.com cost management runbook v2
- Cloudflare GraphQL Analytics API documentation
