# SLO Error Budget & Burn Rate Tracking with D1 and Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want Google SRE-style SLO tracking: sample availability every minute into D1, compute 1h/6h/24h error budget burn rates on demand, and page via PagerDuty when the burn rate is high enough to exhaust the monthly budget ahead of schedule — all without Prometheus or Grafana.

## Context

- SLO: 99.9% monthly availability (43.8 min downtime budget)
- Workers Cron samples endpoints every minute (or reuses health-check data from `workers-health-check-dashboard-d1-kv.md`)
- D1 table `availability_samples` holds 1/0 per endpoint per minute
- Workers fetch handler computes burn rates over multiple windows
- PagerDuty Events API v2 sends critical alerts
- Stack: Workers (TypeScript), D1, Wrangler 3.x

---

## Step 1 — D1 Schema

```sql
-- migrations/0001_slo.sql
CREATE TABLE IF NOT EXISTS availability_samples (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  endpoint    TEXT    NOT NULL,
  ok          INTEGER NOT NULL,   -- 1 = good minute, 0 = bad minute
  sampled_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_samples_endpoint_time
  ON availability_samples (endpoint, sampled_at DESC);

-- Materialised SLO config (one row per endpoint)
CREATE TABLE IF NOT EXISTS slo_config (
  endpoint      TEXT    PRIMARY KEY,
  slo_target    REAL    NOT NULL DEFAULT 0.999,  -- 99.9%
  window_days   INTEGER NOT NULL DEFAULT 30
);
```

```bash
wrangler d1 create slo-tracking-db
wrangler d1 migrations apply slo-tracking-db --remote
```

## Step 2 — wrangler.toml

```toml
name = "slo-tracker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding = "DB"
database_name = "slo-tracking-db"
database_id   = "<your-d1-id>"

[vars]
ENDPOINTS = "https://api.example.com/health,https://app.example.com/ping"
PAGERDUTY_ROUTING_KEY = ""
# Fast burn: 1h burn rate > 14.4x SLO consumption rate (burns 2% budget in 1h → gone in 2.5 days)
FAST_BURN_THRESHOLD  = "14.4"
# Slow burn: 6h burn rate > 6x
SLOW_BURN_THRESHOLD  = "6.0"

[[triggers.crons]]
crons = ["* * * * *"]
```

## Step 3 — Sampling Cron

```typescript
// src/sampler.ts
export async function sampleEndpoints(
  db: D1Database,
  endpoints: string[]
): Promise<void> {
  const results = await Promise.all(
    endpoints.map(async url => {
      try {
        const res = await fetch(url, {
          signal: AbortSignal.timeout(5_000),
          headers: { 'User-Agent': 'orchords-slo-sampler/1.0' },
        });
        return { endpoint: url, ok: res.ok ? 1 : 0 };
      } catch {
        return { endpoint: url, ok: 0 };
      }
    })
  );

  const stmt = db.prepare(
    `INSERT INTO availability_samples (endpoint, ok, sampled_at) VALUES (?, ?, datetime('now'))`
  );
  await db.batch(results.map(r => stmt.bind(r.endpoint, r.ok)));

  // Prune older than 35 days (keep buffer beyond 30-day window)
  await db
    .prepare(`DELETE FROM availability_samples WHERE sampled_at < datetime('now', '-35 days')`)
    .run();
}
```

## Step 4 — Burn Rate Computation

```typescript
// src/burn-rate.ts
export interface BurnRateResult {
  endpoint:      string;
  slo_target:    number;
  error_budget_minutes: number;     // total bad minutes allowed in window
  consumed_minutes:     number;     // bad minutes used so far this window
  budget_remaining_pct: number;     // 0–100
  burn_rate_1h:  number;            // multiples of "normal" consumption rate
  burn_rate_6h:  number;
  burn_rate_24h: number;
}

export async function computeBurnRates(
  db: D1Database,
  endpoint: string,
  sloTarget: number = 0.999,
  windowDays: number = 30
): Promise<BurnRateResult> {
  const windowMinutes = windowDays * 24 * 60;            // 43200
  const errorBudgetMinutes = windowMinutes * (1 - sloTarget); // 43.2

  // Total bad minutes in the current rolling window
  const total = await db
    .prepare(
      `SELECT
         COUNT(*) AS total,
         SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS bad
       FROM availability_samples
       WHERE endpoint = ?
         AND sampled_at >= datetime('now', '-${windowDays} days')`
    )
    .bind(endpoint)
    .first<{ total: number; bad: number }>();

  const consumedMinutes = total?.bad ?? 0;
  const budgetRemainingPct =
    Math.max(0, ((errorBudgetMinutes - consumedMinutes) / errorBudgetMinutes) * 100);

  // Bad-minute counts over short windows for burn rate
  async function badInLastNMinutes(n: number): Promise<number> {
    const row = await db
      .prepare(
        `SELECT SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS bad
         FROM availability_samples
         WHERE endpoint = ?
           AND sampled_at >= datetime('now', '-${n} minutes')`
      )
      .bind(endpoint)
      .first<{ bad: number }>();
    return row?.bad ?? 0;
  }

  // Burn rate = (observed error rate in window) / (allowed error rate)
  // allowed = (1 - sloTarget); observed_1h = bad_1h / 60
  const allowed = 1 - sloTarget;
  const bad1h   = await badInLastNMinutes(60);
  const bad6h   = await badInLastNMinutes(360);
  const bad24h  = await badInLastNMinutes(1440);

  const burnRate1h  = bad1h  > 0 ? (bad1h  / 60)   / allowed : 0;
  const burnRate6h  = bad6h  > 0 ? (bad6h  / 360)  / allowed : 0;
  const burnRate24h = bad24h > 0 ? (bad24h / 1440) / allowed : 0;

  return {
    endpoint,
    slo_target:    sloTarget,
    error_budget_minutes: errorBudgetMinutes,
    consumed_minutes:     consumedMinutes,
    budget_remaining_pct: budgetRemainingPct,
    burn_rate_1h:  burnRate1h,
    burn_rate_6h:  burnRate6h,
    burn_rate_24h: burnRate24h,
  };
}
```

## Step 5 — PagerDuty Alert and Main Worker

```typescript
// src/index.ts
import { sampleEndpoints } from './sampler';
import { computeBurnRates, BurnRateResult } from './burn-rate';

interface Env {
  DB: D1Database;
  ENDPOINTS: string;
  PAGERDUTY_ROUTING_KEY: string;
  FAST_BURN_THRESHOLD: string;
  SLOW_BURN_THRESHOLD: string;
}

async function pageDuty(routingKey: string, result: BurnRateResult, level: 'fast' | 'slow'): Promise<void> {
  if (!routingKey) return;
  await fetch('https://events.pagerduty.com/v2/enqueue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      routing_key: routingKey,
      event_action: 'trigger',
      dedup_key: `slo-burn-${result.endpoint}-${level}`,
      payload: {
        summary: `[${level.toUpperCase()} BURN] ${result.endpoint} — budget ${result.budget_remaining_pct.toFixed(1)}% remaining`,
        severity: level === 'fast' ? 'critical' : 'warning',
        source: 'cloudflare-workers-slo-tracker',
        custom_details: result,
      },
    }),
  });
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const endpoints   = env.ENDPOINTS.split(',').map(e => e.trim()).filter(Boolean);
    const fastThresh  = parseFloat(env.FAST_BURN_THRESHOLD);
    const slowThresh  = parseFloat(env.SLOW_BURN_THRESHOLD);

    await sampleEndpoints(env.DB, endpoints);

    for (const endpoint of endpoints) {
      const result = await computeBurnRates(env.DB, endpoint);
      console.log(JSON.stringify(result));

      if (result.burn_rate_1h >= fastThresh) {
        await pageDuty(env.PAGERDUTY_ROUTING_KEY, result, 'fast');
      } else if (result.burn_rate_6h >= slowThresh) {
        await pageDuty(env.PAGERDUTY_ROUTING_KEY, result, 'slow');
      }
    }
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const url       = new URL(request.url);
    const endpoints = env.ENDPOINTS.split(',').map(e => e.trim()).filter(Boolean);

    if (url.pathname === '/slo') {
      const results = await Promise.all(
        endpoints.map(ep => computeBurnRates(env.DB, ep))
      );
      return Response.json(results);
    }
    return new Response('Not found', { status: 404 });
  },
};
```

## Anti-patterns

- Sampling more frequently than once per minute — D1 row counts grow fast; sub-minute sampling adds noise without improving accuracy for a 30-day SLO window
- Computing burn rate only over one window — Google SRE recommends multi-window (1h + 6h) to reduce false positives
- Not deduplicating PagerDuty alerts with `dedup_key` — repeated cron runs fire duplicate pages
- Deleting samples older than the SLO window too aggressively — keep 35 days to allow queries near a window boundary

## Gotchas

- D1 `COUNT(*)` with a `datetime()` filter performs a full table scan unless the index covers both `endpoint` and `sampled_at`; the compound index in the schema is essential
- PagerDuty `dedup_key` is per routing-key; use a stable, content-based key (`endpoint + level`) to avoid storm pages
- The burn rate formula assumes a Poisson failure model; correlated outages (e.g. entire region down) make both fast and slow rates spike simultaneously — that's the expected behaviour
- Workers Cron clock jitter can be ±30s; samples may cluster slightly; this is negligible for 30-day SLO math

## Verification

```bash
# Check availability sample counts by endpoint
wrangler d1 execute slo-tracking-db --remote \
  --command "SELECT endpoint, COUNT(*) as total, SUM(ok) as good FROM availability_samples GROUP BY endpoint;"

# Simulate failures: mark last 15 minutes as bad for testing
wrangler d1 execute slo-tracking-db --remote \
  --command "UPDATE availability_samples SET ok=0 WHERE sampled_at >= datetime('now', '-15 minutes') AND endpoint='https://api.example.com/health';"

# Hit the SLO endpoint
curl -s https://slo-tracker.<your-subdomain>.workers.dev/slo | jq .

# Confirm cron firing
wrangler tail slo-tracker --format pretty | grep burn_rate
```

## Related

- `documentation/categories/monitoring/workers-health-check-dashboard-d1-kv.md`
- `documentation/categories/monitoring/workers-anomaly-detection-analytics-engine.md`

## Sources

- https://sre.google/workbook/alerting-on-slos/
- https://developers.cloudflare.com/d1/
- https://developer.pagerduty.com/api-reference/368ae3d938c9e-send-an-event-to-pager-duty
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
