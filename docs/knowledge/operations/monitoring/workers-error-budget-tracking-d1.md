# SLO Error Budget Tracking with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You have defined availability and latency SLOs but have no automated way to track error budget consumption in real time, alert when the burn rate is dangerously high across multiple windows, or expose a dashboard endpoint with current budget remaining. You want all of this inside Cloudflare Workers without an external monitoring platform.

## Context

SLO error budgets track the cumulative acceptable failure rate over a rolling window. A burn rate > 1 means the budget is depleting faster than allowed. Multi-window burn rate alerts (1h, 6h, 72h) catch both sudden spikes and slow-burn degradation. D1 provides a SQLite-compatible database for persisting SLO events. Workers Cron evaluates burn rates on a schedule and sends notifications when thresholds are exceeded.

## Solution

### wrangler.toml

```toml
name = "slo-tracker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding  = "SLO_DB"
database_name = "slo_events"
database_id   = "YOUR_D1_DATABASE_ID"

[[triggers]]
crons = ["*/5 * * * *"]   # evaluate burn rate every 5 minutes

[vars]
SLO_ALERT_WEBHOOK = "https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

### D1 schema

```sql
-- migrations/0001_slo_events.sql

CREATE TABLE IF NOT EXISTS slo_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  slo_id       TEXT    NOT NULL,
  event_type   TEXT    NOT NULL CHECK(event_type IN ('good','bad')),
  latency_ms   REAL,
  recorded_at  INTEGER NOT NULL   -- Unix milliseconds
);

CREATE INDEX idx_slo_events_slo_recorded
  ON slo_events (slo_id, recorded_at);

CREATE TABLE IF NOT EXISTS burn_rate_alerts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  slo_id       TEXT    NOT NULL,
  window_hours INTEGER NOT NULL,
  burn_rate    REAL    NOT NULL,
  fired_at     INTEGER NOT NULL,
  resolved_at  INTEGER
);
```

### SLO definition types

```typescript
// src/slo.ts

export interface SLODefinition {
  id: string;
  name: string;
  // Availability SLO: ratio of good requests to total
  availabilityTarget: number;   // e.g. 0.999 = 99.9%
  // Latency SLO: fraction of requests under threshold
  latencyTargetMs: number;      // e.g. 200
  latencyTarget: number;        // e.g. 0.95 = 95th percentile under 200ms
  // Error budget window
  windowDays: number;           // e.g. 30
}

export const SLOS: SLODefinition[] = [
  {
    id: 'api-availability',
    name: 'API Availability',
    availabilityTarget: 0.999,
    latencyTargetMs: 0,
    latencyTarget: 0,
    windowDays: 30,
  },
  {
    id: 'api-latency-p95',
    name: 'API Latency P95',
    availabilityTarget: 0,
    latencyTargetMs: 200,
    latencyTarget: 0.95,
    windowDays: 30,
  },
];
```

### Recording SLO events from the request path

```typescript
// src/recorder.ts

import type { SLODefinition } from './slo';

interface Env {
  SLO_DB: D1Database;
}

export async function recordSLOEvent(
  db: D1Database,
  sloId: string,
  latencyMs: number,
  statusCode: number,
  slo: SLODefinition
): Promise<void> {
  // Availability: 5xx responses are bad events
  const availabilityBad = statusCode >= 500;
  // Latency: requests exceeding threshold are bad events
  const latencyBad = slo.latencyTargetMs > 0 && latencyMs > slo.latencyTargetMs;

  const eventType = availabilityBad || latencyBad ? 'bad' : 'good';

  await db.prepare(
    `INSERT INTO slo_events (slo_id, event_type, latency_ms, recorded_at)
     VALUES (?, ?, ?, ?)`
  ).bind(sloId, eventType, latencyMs, Date.now()).run();
}
```

### Burn rate calculation

```typescript
// src/burnrate.ts

export interface BurnRateResult {
  sloId: string;
  windowHours: number;
  burnRate: number;
  errorBudgetRemainingPct: number;
  goodEvents: number;
  totalEvents: number;
}

const BURN_WINDOWS_HOURS = [1, 6, 72];

// Fast-burn thresholds (Google SRE Workbook chapter 5)
const BURN_THRESHOLDS: Record<number, number> = {
  1:  14,  // 1h window: burn rate >14 triggers page
  6:   6,  // 6h window: burn rate >6  triggers page
  72:  1,  // 72h window: burn rate >1 triggers ticket
};

export async function calculateBurnRates(
  db: D1Database,
  slo: { id: string; availabilityTarget: number; windowDays: number }
): Promise<BurnRateResult[]> {
  const results: BurnRateResult[] = [];

  for (const windowHours of BURN_WINDOWS_HOURS) {
    const windowMs = windowHours * 60 * 60 * 1000;
    const since    = Date.now() - windowMs;

    const row = await db.prepare(`
      SELECT
        COUNT(*)                                  AS total,
        SUM(CASE WHEN event_type = 'bad' THEN 1 ELSE 0 END) AS bad
      FROM slo_events
      WHERE slo_id = ? AND recorded_at >= ?
    `).bind(slo.id, since).first<{ total: number; bad: number }>();

    if (!row || row.total === 0) continue;

    const errorRate      = row.bad / row.total;
    const allowedError   = 1 - slo.availabilityTarget;
    const burnRate       = allowedError > 0 ? errorRate / allowedError : 0;
    // Remaining budget as a fraction of the 30-day window
    const consumed       = errorRate * windowHours / (slo.windowDays * 24);
    const remainingPct   = Math.max(0, (1 - consumed / allowedError) * 100);

    results.push({
      sloId: slo.id,
      windowHours,
      burnRate,
      errorBudgetRemainingPct: Math.round(remainingPct * 100) / 100,
      goodEvents: row.total - row.bad,
      totalEvents: row.total,
    });
  }

  return results;
}

export function isExhausted(result: BurnRateResult): boolean {
  return result.burnRate > BURN_THRESHOLDS[result.windowHours];
}
```

### Cron handler: evaluate and alert

```typescript
// src/index.ts

import { SLOS } from './slo';
import { calculateBurnRates, isExhausted } from './burnrate';

interface Env {
  SLO_DB: D1Database;
  SLO_ALERT_WEBHOOK: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(evaluateSLOs(env));
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname === '/dashboard') {
      return dashboardEndpoint(env);
    }
    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;

async function evaluateSLOs(env: Env) {
  for (const slo of SLOS) {
    const rates = await calculateBurnRates(env.SLO_DB, slo);
    for (const rate of rates) {
      if (isExhausted(rate)) {
        await sendSlackAlert(env.SLO_ALERT_WEBHOOK, slo.name, rate);
        await env.SLO_DB.prepare(
          `INSERT INTO burn_rate_alerts (slo_id, window_hours, burn_rate, fired_at)
           VALUES (?, ?, ?, ?)`
        ).bind(rate.sloId, rate.windowHours, rate.burnRate, Date.now()).run();
      }
    }
  }
}

async function sendSlackAlert(
  webhook: string,
  sloName: string,
  rate: import('./burnrate').BurnRateResult
) {
  const text =
    `*SLO Alert*: ${sloName}\n` +
    `Window: ${rate.windowHours}h | Burn rate: ${rate.burnRate.toFixed(2)}x\n` +
    `Error budget remaining: ${rate.errorBudgetRemainingPct}%`;
  await fetch(webhook, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
}

async function dashboardEndpoint(env: Env): Promise<Response> {
  const data = await Promise.all(
    SLOS.map(async slo => ({
      slo: slo.id,
      name: slo.name,
      target: slo.availabilityTarget,
      burnRates: await calculateBurnRates(env.SLO_DB, slo),
    }))
  );
  return Response.json({ generatedAt: new Date().toISOString(), slos: data });
}
```

## Implementation Details

- **Event pruning**: D1 does not auto-expire rows. Run a daily cleanup cron: `DELETE FROM slo_events WHERE recorded_at < (unixepoch('now') * 1000 - 30 * 86400000)` to keep the table bounded.
- **Dual-window alerting**: Combining a short window (1h, high threshold) with a long window (72h, burn rate > 1) ensures you catch both sudden catastrophic failures and slow budget drain.
- **D1 write latency**: D1 writes from the Worker request path add 1–5 ms. Use `ctx.waitUntil` to fire-and-forget the insert after returning the response.
- **Alert deduplication**: Query `burn_rate_alerts` for an open alert (no `resolved_at`) before inserting a new one to avoid flooding Slack.

## Anti-patterns

- **Point-in-time SLO calculation**: Calculating SLO compliance only at the end of a month provides no actionable signal during the month. Use rolling windows.
- **Not separating latency and availability SLOs**: Mixing them into a single metric obscures root cause. Track them independently.
- **Purging events too aggressively**: Deleting events older than 1 day breaks multi-day burn rate windows. Keep events for at least `windowDays` days.

## Gotchas

- D1 uses SQLite's `INTEGER` type for timestamps. Store milliseconds as integers; avoid `DATETIME` columns which require format parsing.
- D1 `first<T>()` returns `null` if the query returns no rows. Always handle the null case.
- Worker free tier has a D1 row limit. For high-traffic services, sample events (e.g. record 1 in 10 requests) and multiply counts in the burn rate calculation.
- Slack Incoming Webhooks silently rate-limit to 1 message per second. Batch alerts if multiple SLOs breach simultaneously.

## Verification

```bash
# Apply migration
npx wrangler d1 migrations apply slo_events

# Insert a synthetic bad event
npx wrangler d1 execute slo_events \
  --command "INSERT INTO slo_events (slo_id, event_type, latency_ms, recorded_at) VALUES ('api-availability','bad',0,strftime('%s','now')*1000)"

# Check burn rates via dashboard endpoint
curl https://slo-tracker.example.com/dashboard
```

## Related

- `documentation/docs/policies/monitoring/workers-uptime-monitor-cron-kv.md`
- `documentation/docs/policies/monitoring/workers-structured-logging-analytics-engine.md`
- `documentation/docs/policies/monitoring/workers-anomaly-detection-analytics-engine.md`

## Sources

- https://sre.google/workbook/alerting-on-slos/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
