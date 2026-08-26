# Tracking SLO Error Budget in Workers with Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your team needs real-time SLO error budget visibility without running an external observability stack. You want to record every request outcome (success, error, or latency exceeded) directly from a Cloudflare Worker, query rolling error rates from Analytics Engine, and receive a Slack alert when the weekly error budget is 50% consumed.

---

## Context
Cloudflare Analytics Engine (AE) is a write-optimised time-series store built into the Workers runtime — you emit data points with `env.AE.writeDataPoint()` and query them via the AE SQL API. Pairing AE with a Cron Worker that writes burn-rate snapshots to D1 gives you a durable audit trail alongside fast ad-hoc queries. The SLO model used here is a simple availability SLO: target 99.9% success over a rolling 7-day window, giving a weekly error budget of 0.1% × total requests. The Cron Worker runs every hour, computes burn rate since the start of the week, and fires a Slack webhook when the budget is half gone.

---

## Section 1 — D1 Schema & wrangler.toml

```sql
-- error_budget_snapshots table
CREATE TABLE IF NOT EXISTS error_budget_snapshots (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  week_start   TEXT    NOT NULL,           -- ISO-8601 Monday 00:00 UTC
  sampled_at   TEXT    NOT NULL,           -- ISO-8601 snapshot timestamp
  total_reqs   INTEGER NOT NULL,
  error_reqs   INTEGER NOT NULL,
  error_rate   REAL    NOT NULL,           -- 0.0 – 1.0
  budget_pct   REAL    NOT NULL,           -- % of weekly budget consumed
  alerted      INTEGER NOT NULL DEFAULT 0 -- 1 once Slack alert sent
);

CREATE INDEX IF NOT EXISTS idx_ebs_week ON error_budget_snapshots (week_start);
```

```toml
# wrangler.toml
name = "slo-tracker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "slo_events"

[[d1_databases]]
binding    = "DB"
database_name = "slo-tracker-db"
database_id   = "<your-d1-id>"

[vars]
SLACK_WEBHOOK = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
SLO_TARGET    = "0.999"
```

---

## Section 2 — Request-outcome recording middleware

```typescript
// src/index.ts
export interface Env {
  AE: AnalyticsEngineDataset;
  DB: D1Database;
  SLACK_WEBHOOK: string;
  SLO_TARGET: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    let outcome: 'success' | 'error' | 'latency_exceeded' = 'success';
    let response: Response;

    try {
      response = await handleRequest(request, env);
      if (!response.ok) outcome = 'error';
    } catch (err) {
      outcome = 'error';
      response = new Response('Internal Server Error', { status: 500 });
    }

    const latencyMs = Date.now() - start;
    if (latencyMs > 2000 && outcome === 'success') outcome = 'latency_exceeded';

    // Write to Analytics Engine: blob1=outcome, double1=1 (count), double2=latency
    ctx.waitUntil(
      Promise.resolve(
        env.AE.writeDataPoint({
          blobs: [outcome, request.method, new URL(request.url).pathname],
          doubles: [1, latencyMs],
          indexes: [outcome],
        })
      )
    );

    return response;
  },

  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runBudgetSnapshot(env));
  },
};

async function handleRequest(request: Request, _env: Env): Promise<Response> {
  return new Response(JSON.stringify({ status: 'ok' }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## Section 3 — Cron budget-burn Worker

```typescript
// src/budget.ts  (called from scheduled handler above)
const AE_SQL_ENDPOINT =
  'https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql';

async function queryAE(sql: string, apiToken: string): Promise<any> {
  const res = await fetch(AE_SQL_ENDPOINT, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query: sql }),
  });
  if (!res.ok) throw new Error(`AE query failed: ${res.status}`);
  return res.json();
}

export async function runBudgetSnapshot(env: Env): Promise<void> {
  // Week boundaries (Monday 00:00 UTC)
  const now = new Date();
  const dayOfWeek = now.getUTCDay(); // 0=Sun
  const daysFromMonday = (dayOfWeek + 6) % 7;
  const weekStart = new Date(now);
  weekStart.setUTCDate(now.getUTCDate() - daysFromMonday);
  weekStart.setUTCHours(0, 0, 0, 0);
  const weekStartISO = weekStart.toISOString();

  const apiToken = (env as any).CF_API_TOKEN as string;

  // Query AE for counts since week start
  const sql = `
    SELECT
      COUNT()                                                        AS total,
      SUM(double1) FILTER (WHERE blob1 = 'error')                   AS errors,
      SUM(double1) FILTER (WHERE blob1 = 'latency_exceeded')        AS latency_exceeded
    FROM slo_events
    WHERE timestamp >= toDateTime('${weekStartISO}')
  `;

  const data = await queryAE(sql, apiToken);
  const row = data.data?.[0] ?? { total: 0, errors: 0, latency_exceeded: 0 };

  const total = Number(row.total) || 0;
  const errorCount = Number(row.errors) + Number(row.latency_exceeded) || 0;
  const errorRate = total > 0 ? errorCount / total : 0;

  const sloTarget = parseFloat(env.SLO_TARGET);
  const allowedErrorRate = 1 - sloTarget; // 0.001 for 99.9%

  // Budget consumed as a fraction of the weekly allowance
  // budget_pct = error_rate / allowed_error_rate  (>1.0 = budget exhausted)
  const budgetPct = allowedErrorRate > 0 ? errorRate / allowedErrorRate : 0;

  // Persist snapshot
  await env.DB.prepare(
    `INSERT INTO error_budget_snapshots
       (week_start, sampled_at, total_reqs, error_reqs, error_rate, budget_pct)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(weekStartISO, now.toISOString(), total, errorCount, errorRate, budgetPct)
    .run();

  // Alert if ≥50% consumed and no alert sent this week yet
  if (budgetPct >= 0.5) {
    const alerted = await env.DB.prepare(
      `SELECT 1 FROM error_budget_snapshots
       WHERE week_start = ? AND alerted = 1 LIMIT 1`
    )
      .bind(weekStartISO)
      .first();

    if (!alerted) {
      await sendSlackAlert(env.SLACK_WEBHOOK, budgetPct, errorRate, total);
      await env.DB.prepare(
        `UPDATE error_budget_snapshots SET alerted = 1
         WHERE week_start = ? AND alerted = 0`
      )
        .bind(weekStartISO)
        .run();
    }
  }
}

async function sendSlackAlert(
  webhook: string,
  budgetPct: number,
  errorRate: number,
  total: number
): Promise<void> {
  const pct = (budgetPct * 100).toFixed(1);
  const er = (errorRate * 100).toFixed(3);
  await fetch(webhook, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `*SLO Error Budget Alert* — ${pct}% of weekly budget consumed`,
      blocks: [
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text:
              `*Error budget at ${pct}%* (target 99.9% availability)\n` +
              `Current error rate: \`${er}%\` over ${total.toLocaleString()} requests this week.\n` +
              'Investigate immediately to avoid SLO breach.',
          },
        },
      ],
    }),
  });
}
```

---

## Anti-patterns
- **Querying AE from the hot path** — AE writes are non-blocking (`waitUntil`); never await them inline or you add latency to every request.
- **Using KV for time-series data** — KV is key-value; for aggregation queries you need Analytics Engine or D1.
- **Resetting alerted flag mid-week** — only reset it at week boundary, otherwise you send duplicate alerts.
- **Storing raw AE results in D1 row by row** — write only hourly snapshots to D1, not every AE data point.

---

## Gotchas
- Analytics Engine SQL uses `toDateTime()` not standard ISO cast syntax — check the AE SQL reference.
- `CF_API_TOKEN` must have `Analytics Engine Read` permission scope to query AE via REST.
- The `FILTER (WHERE ...)` clause in AE SQL requires dataset schema version ≥ 2024-06.
- `writeDataPoint` is fire-and-forget from the Worker runtime; dropped points (during surge) are not retried.

---

## Verification
```bash
# Deploy
npx wrangler deploy

# Tail live logs and trigger a few requests
npx wrangler tail --format pretty
curl https://<worker>.workers.dev/

# Trigger the Cron manually
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+*+*+*+*"

# Check D1 snapshot
npx wrangler d1 execute slo-tracker-db \
  --command "SELECT * FROM error_budget_snapshots ORDER BY sampled_at DESC LIMIT 5;"
```

---

## Related
- `github-issue-sla-breach-cron-workers.md`
- `on-call-rotation-workers-pagerduty-slack.md`

---

## Sources
- Cloudflare Analytics Engine docs — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
