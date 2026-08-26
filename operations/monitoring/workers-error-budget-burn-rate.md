# Error Budget Burn Rate Alerting in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a 99.9 % availability SLO for your API. Last Tuesday the error rate sat at 0.5 % for four hours — not bad enough to page anyone (your static threshold was 1 %), but it consumed 14.4 hours of your monthly error budget in a single afternoon. By the time you noticed, you had no budget left for the planned schema migration later that week. You need burn-rate alerting: alerts that fire when you are consuming your error budget *faster* than you can afford, even when the absolute error rate looks benign.

## Context

The burn-rate model (from Google SRE Workbook, Chapter 5) works as follows:

- **Error budget** = `(1 - SLO) × window`. For 99.9 % over 30 days: 0.001 × 30 × 24 × 60 = 43.2 minutes of allowable downtime.
- **Burn rate** = `observed error rate / (1 - SLO)`. A burn rate of 1 means you consume your budget at exactly the right pace. A burn rate of 14 means you will exhaust it 14 × faster — in 2.14 days instead of 30.
- **Multi-window multi-burn-rate (MWMB)** uses two time windows per alert tier: a short window catches fast burns; a long window filters transient spikes.

Stack:
- **Analytics Engine** — error count and request count per minute (written by the main Worker)
- **D1** — weekly SLO report persistence
- **KV** — alert state and burn-rate cache
- **Queue** — alert fan-out to PagerDuty and Slack

## Solution

```typescript
// error-budget.ts
import type { D1Database, KVNamespace, AnalyticsEngineDataset, Queue } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  BUDGET_KV: KVNamespace;
  AE: AnalyticsEngineDataset;
  ALERT_QUEUE: Queue;
  SLO_TARGET: string;        // e.g. "0.999"
  SLO_WINDOW_DAYS: string;   // e.g. "30"
  FAST_BURN_RATE: string;    // e.g. "14"  (triggers at 1-hour window)
  SLOW_BURN_RATE: string;    // e.g. "3"   (triggers at 6-hour window)
  CF_ACCOUNT_ID: string;
  AE_DATASET: string;
  CF_API_TOKEN: string;
}

// ── types ─────────────────────────────────────────────────────────────────────

interface BurnRateResult {
  windowHours: number;
  burnRate: number;
  errorRate: number;
  totalRequests: number;
  totalErrors: number;
}

interface AlertTier {
  name: 'fast' | 'slow';
  burnRateThreshold: number;
  shortWindowHours: number;
  longWindowHours: number;
}

const ALERT_TIERS: AlertTier[] = [
  { name: 'fast', burnRateThreshold: 14, shortWindowHours: 1,  longWindowHours: 5  },
  { name: 'slow', burnRateThreshold: 3,  shortWindowHours: 6,  longWindowHours: 3 * 6 },
];

// ── Analytics Engine SQL query ────────────────────────────────────────────────
// Workers Analytics Engine exposes a SQL API; we query it for error and total
// request counts over a sliding window.

async function queryAe(
  accountId: string,
  dataset: string,
  token: string,
  sql: string
): Promise<Array<Record<string, unknown>>> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'text/plain' },
      body: sql,
    }
  );
  if (!res.ok) throw new Error(`AE SQL error ${res.status}: ${await res.text()}`);
  const data = await res.json<{ data: Array<Record<string, unknown>> }>();
  return data.data;
}

// ── burn rate calculation ─────────────────────────────────────────────────────

async function calcBurnRate(
  env: Env,
  windowHours: number
): Promise<BurnRateResult> {
  const slo = parseFloat(env.SLO_TARGET ?? '0.999');
  const errorBudget = 1 - slo; // 0.001 for 99.9 % SLO

  const rows = await queryAe(
    env.CF_ACCOUNT_ID,
    env.AE_DATASET,
    env.CF_API_TOKEN,
    `SELECT
       SUM(double1) AS total_requests,
       SUM(CASE WHEN blob1 = 'error' THEN double1 ELSE 0 END) AS total_errors
     FROM ${env.AE_DATASET}
     WHERE timestamp > NOW() - INTERVAL '${windowHours}' HOUR
       AND index1 = 'request'`
  );

  const totalRequests = Number(rows[0]?.total_requests ?? 0);
  const totalErrors   = Number(rows[0]?.total_errors   ?? 0);

  if (totalRequests === 0) {
    return { windowHours, burnRate: 0, errorRate: 0, totalRequests: 0, totalErrors: 0 };
  }

  const errorRate = totalErrors / totalRequests;
  const burnRate  = errorRate / errorBudget;

  return { windowHours, burnRate, errorRate, totalRequests, totalErrors };
}

// ── multi-window multi-burn-rate alert logic ──────────────────────────────────
// Both the short AND the long window must exceed the burn-rate threshold before
// an alert fires. This eliminates transient spikes (caught only in the short
// window) while still reacting quickly to sustained burns.

async function evaluateTier(
  env: Env,
  tier: AlertTier
): Promise<{ fire: boolean; short: BurnRateResult; long: BurnRateResult }> {
  const [short, long] = await Promise.all([
    calcBurnRate(env, tier.shortWindowHours),
    calcBurnRate(env, tier.longWindowHours),
  ]);

  const fire =
    short.burnRate >= tier.burnRateThreshold &&
    long.burnRate  >= tier.burnRateThreshold;

  return { fire, short, long };
}

// ── alert deduplication ───────────────────────────────────────────────────────
// KV key per tier; TTL matches the short window so the alert re-fires if the
// burn continues beyond one window.

async function isAlertActive(kv: KVNamespace, tier: AlertTier): Promise<boolean> {
  return (await kv.get(`alert:burn:${tier.name}`)) !== null;
}

async function setAlertActive(kv: KVNamespace, tier: AlertTier): Promise<void> {
  await kv.put(`alert:burn:${tier.name}`, '1', {
    expirationTtl: tier.shortWindowHours * 3600,
  });
}

// ── error budget remaining endpoint ──────────────────────────────────────────

async function budgetRemaining(env: Env): Promise<{
  slo: number;
  windowDays: number;
  budgetMinutes: number;
  consumedMinutes: number;
  remainingPercent: number;
}> {
  const slo        = parseFloat(env.SLO_TARGET   ?? '0.999');
  const windowDays = parseInt(env.SLO_WINDOW_DAYS ?? '30',  10);
  const sloWindow  = windowDays * 24 * 60; // minutes
  const budget     = (1 - slo) * sloWindow;

  const rows = await queryAe(
    env.CF_ACCOUNT_ID,
    env.AE_DATASET,
    env.CF_API_TOKEN,
    `SELECT
       SUM(double1) AS total_requests,
       SUM(CASE WHEN blob1 = 'error' THEN double1 ELSE 0 END) AS total_errors
     FROM ${env.AE_DATASET}
     WHERE timestamp > NOW() - INTERVAL '${windowDays * 24}' HOUR
       AND index1 = 'request'`
  );

  const totalRequests = Number(rows[0]?.total_requests ?? 0);
  const totalErrors   = Number(rows[0]?.total_errors   ?? 0);
  const errorRate     = totalRequests > 0 ? totalErrors / totalRequests : 0;
  const consumedMinutes = errorRate * sloWindow;
  const remainingPercent = Math.max(0, ((budget - consumedMinutes) / budget) * 100);

  return { slo, windowDays, budgetMinutes: budget, consumedMinutes, remainingPercent };
}

// ── weekly SLO report cron ────────────────────────────────────────────────────

async function writeWeeklyReport(env: Env): Promise<void> {
  const remaining = await budgetRemaining(env);
  const fastBurn  = await calcBurnRate(env, 1);
  const slowBurn  = await calcBurnRate(env, 168); // 7 days
  const weekTs    = Math.floor(Date.now() / 1000);

  await env.DB
    .prepare(
      `INSERT INTO slo_reports
         (ts, slo, budget_minutes, consumed_minutes, remaining_pct, burn_1h, burn_7d)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      weekTs,
      remaining.slo,
      remaining.budgetMinutes,
      remaining.consumedMinutes,
      remaining.remainingPercent,
      fastBurn.burnRate,
      slowBurn.burnRate
    )
    .run();
}

// ── main scheduled handler ────────────────────────────────────────────────────

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Weekly SLO report (cron: 0 9 * * MON).
    if (event.cron === '0 9 * * 1') {
      ctx.waitUntil(writeWeeklyReport(env));
      return;
    }

    // Evaluate burn rates every minute.
    for (const tier of ALERT_TIERS) {
      const { fire, short, long } = await evaluateTier(env, tier);

      // Write burn-rate metrics to AE for dashboards.
      env.AE.writeDataPoint({
        blobs: [tier.name, 'burn_rate'],
        doubles: [short.burnRate, long.burnRate, short.errorRate],
        indexes: ['slo'],
      });

      if (fire) {
        const alreadyActive = await isAlertActive(env.BUDGET_KV, tier);
        if (!alreadyActive) {
          await setAlertActive(env.BUDGET_KV, tier);
          await env.ALERT_QUEUE.send({
            type: `slo_burn_${tier.name}`,
            tier: tier.name,
            burnRateThreshold: tier.burnRateThreshold,
            shortWindow: { hours: tier.shortWindowHours, ...short },
            longWindow: { hours: tier.longWindowHours, ...long },
            sloTarget: parseFloat(env.SLO_TARGET ?? '0.999'),
            firedAt: new Date().toISOString(),
          });
        }
      }
    }
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/slo/budget') {
      return Response.json(await budgetRemaining(env));
    }

    if (url.pathname === '/slo/burn-rates') {
      const [fast1h, slow6h, monthly] = await Promise.all([
        calcBurnRate(env, 1),
        calcBurnRate(env, 6),
        calcBurnRate(env, parseInt(env.SLO_WINDOW_DAYS ?? '30', 10) * 24),
      ]);
      return Response.json({ '1h': fast1h, '6h': slow6h, '30d': monthly });
    }

    if (url.pathname === '/slo/reports') {
      const rows = await env.DB
        .prepare(`SELECT * FROM slo_reports ORDER BY ts DESC LIMIT 12`)
        .all();
      return Response.json({ reports: rows.results });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

**MWMB alert logic** — the Google SRE Workbook recommends requiring the burn rate to exceed the threshold in both a short and a long window before alerting. This eliminates two failure modes: (1) a 30-second error spike that exceeds the fast-burn rate in the 1-hour window but not the 5-hour window; (2) a slow creep that exceeds the slow-burn rate in the 18-hour window but has already self-healed in the 6-hour window.

**Alert TTL = short window** — the KV cooldown key expires after `shortWindowHours × 3600` seconds. If the burn rate is still elevated after one short window, the alert re-fires. This balances deduplication (no page storms) with re-escalation (continued incidents get re-paged).

**AE SQL for error counts** — the Worker already writes `writeDataPoint({ blobs: ['error'|'success'], doubles: [1], indexes: ['request'] })` on every request. The AE SQL query aggregates these using a `CASE` expression. This avoids storing error counts in D1 separately.

**Cron discrimination** — a single Worker can respond to multiple cron schedules. The `event.cron` string matches the wrangler.toml trigger pattern. The weekly report cron (`0 9 * * 1`) fires only on Mondays at 09:00 UTC; the main burn-rate check runs on `* * * * *`.

## Anti-patterns

- **Alerting on raw error rate**: `if (errorRate > 0.001)` misses the budget-velocity problem. A 0.08 % error rate for 12 hours is fine. A 0.08 % error rate for 30 days exhausts your budget twice over.
- **Single-window burn rate**: alerting only on a 1-hour window fires for transient spikes (deploy flap, health-check blip). The long window provides a reality check.
- **No alert cooldown**: burn rate can oscillate around the threshold, firing an alert every minute. The KV TTL-based cooldown collapses all alerts within one short window into a single page.
- **Querying D1 for request counts**: D1 is not a time-series database. Analytics Engine is purpose-built for high-cardinality metric aggregation and should be the single source of truth for request/error counts.

## Gotchas

- **AE SQL eventual consistency**: Analytics Engine data has a ~1-minute ingestion lag. Your 1-hour burn-rate window effectively covers the last 59 minutes. This is acceptable for burn-rate alerting but not for real-time dashboards.
- **`event.cron` format matching**: the `event.cron` string uses the exact cron pattern from `wrangler.toml`, including spaces. `'0 9 * * 1'` and `'0 9 * * MON'` are different strings — use whichever format wrangler stores.
- **D1 weekly report table**: create the table before deploying: `CREATE TABLE IF NOT EXISTS slo_reports (ts INTEGER, slo REAL, budget_minutes REAL, consumed_minutes REAL, remaining_pct REAL, burn_1h REAL, burn_7d REAL);`
- **Burn rate of 0 at low traffic**: if `totalRequests = 0` (e.g., overnight for a B2B service), the burn rate is 0 and no alert fires. This is correct — zero traffic means zero errors and zero budget consumption.

## Verification

```bash
# Check current budget remaining.
curl -s https://api.example.com/slo/budget | jq .

# Check live burn rates across windows.
curl -s https://api.example.com/slo/burn-rates | jq .

# Inject synthetic errors to trigger fast burn alert.
# (Requires a test harness that writes error events to AE.)
npx ts-node scripts/inject-errors.ts --rate 0.05 --duration 65m

# Confirm the KV alert flag is set.
npx wrangler kv key get --namespace-id=<ID> "alert:burn:fast"

# Query AE for SLO metric history.
curl -s "https://api.cloudflare.com/client/v4/accounts/<ACCT>/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  --data "SELECT blob1, double1 as burn_rate, timestamp FROM <DATASET> WHERE index1='slo' ORDER BY timestamp DESC LIMIT 20"

# Pull weekly SLO reports from D1.
npx wrangler d1 execute <DB_NAME> \
  --command "SELECT ts, remaining_pct, burn_1h, burn_7d FROM slo_reports ORDER BY ts DESC LIMIT 4;"
```

## Related

- `documentation/categories/monitoring/workers-anomaly-detection-zscore.md` — statistical alerting
- `documentation/categories/monitoring/on-call-rotation-pagerduty.md` — alert routing and escalation
- `documentation/categories/monitoring/metric-aggregation-cron-d1.md` — metric ingestion
- `documentation/categories/monitoring/cost-per-request-tracking.md` — per-request cost in the SLO context

## Sources

- Google SRE Workbook, Chapter 5: Alerting on SLOs — https://sre.google/workbook/alerting-on-slos/
- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- D1 Database — https://developers.cloudflare.com/d1/
