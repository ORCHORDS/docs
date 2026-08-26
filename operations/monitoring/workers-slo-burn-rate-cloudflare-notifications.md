# Workers SLO Burn-Rate Alerting via Cloudflare Notifications

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
An error budget can be exhausted hours before a Prometheus alert fires because alert thresholds are set on instantaneous error rate rather than burn rate. Combining Analytics Engine SQL queries with Cloudflare's Notifications API inside a Cron Trigger Worker implements multi-window burn-rate alerting without any external infrastructure.

## Context
The multi-window burn-rate model (Google SRE Workbook ch. 5) fires when fast burn and slow burn windows both exceed their thresholds simultaneously, eliminating most false positives. Here the "Prometheus" role is played by Analytics Engine queries and the "Alertmanager" role is played by a Cron Trigger Worker that calls the Cloudflare Notifications API to dispatch to a webhook, PagerDuty, or Slack.

## SLO Budget Definition

Define the SLO and error budget parameters as constants shared across the alerting Worker.

```typescript
// src/slo-config.ts
export const SLO = {
  target:            0.999,       // 99.9% availability
  windowDays:        30,
  shortWindowMins:   5,
  longWindowMins:    60,
  // burn rates that consume 5% of the monthly budget in each window
  shortBurnRate:     14.4,        // 5% budget in 1 h
  longBurnRate:       6,          // 5% budget in 6 h
  dataset:           'worker_requests',  // AE dataset name
  accountId:         '',          // filled from env
} as const;

export type BurnRateResult = {
  shortRate: number;
  longRate:  number;
  shortErrorRate: number;
  longErrorRate:  number;
};
```

## Querying Analytics Engine for Burn Rate

```typescript
// src/ae-burn-rate.ts
import { SLO } from './slo-config';

const AE_SQL_BASE = 'https://api.cloudflare.com/client/v4/accounts';

export async function computeBurnRate(
  accountId: string,
  apiToken: string,
): Promise<BurnRateResult> {
  const errorBudget = 1 - SLO.target;

  const query = `
    SELECT
      countIf(blob3 = 'error') / count()               AS short_error_rate,
      countIf(blob3 = 'error', timestamp > now() - INTERVAL '${SLO.longWindowMins}' MINUTE)
        / countIf(timestamp > now() - INTERVAL '${SLO.longWindowMins}' MINUTE) AS long_error_rate
    FROM ${SLO.dataset}
    WHERE timestamp > now() - INTERVAL '${SLO.longWindowMins}' MINUTE
  `;
  // blob3 holds the outcome field written by the observed Worker

  const resp = await fetch(
    `${AE_SQL_BASE}/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization:  `Bearer ${apiToken}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: query,
    }
  );

  if (!resp.ok) throw new Error(`AE SQL error: ${resp.status} ${await resp.text()}`);
  const data: any = await resp.json();
  const row = data.data?.[0] ?? {};

  const shortErrorRate = parseFloat(row.short_error_rate ?? '0');
  const longErrorRate  = parseFloat(row.long_error_rate  ?? '0');

  return {
    shortErrorRate,
    longErrorRate,
    shortRate: shortErrorRate / errorBudget,
    longRate:  longErrorRate  / errorBudget,
  };
}
```

## Multi-window Burn-Rate Decision

```typescript
// src/burn-rate-check.ts
import { SLO, BurnRateResult } from './slo-config';

export type AlertSeverity = 'page' | 'ticket' | 'none';

export function evaluateBurnRate(result: BurnRateResult): AlertSeverity {
  const { shortRate, longRate } = result;

  // Fast burn: 5% budget in 1 h — page immediately
  if (shortRate >= SLO.shortBurnRate && longRate >= SLO.longBurnRate) {
    return 'page';
  }

  // Slow burn: 10% budget in 6 h — open a ticket
  if (shortRate >= 3 && longRate >= 1) {
    return 'ticket';
  }

  return 'none';
}
```

## Dispatching via Cloudflare Notifications API

```typescript
// src/notify.ts
const NOTIF_BASE = 'https://api.cloudflare.com/client/v4/accounts';

export async function sendAlert(
  accountId: string,
  apiToken: string,
  policyId: string,
  message: string,
): Promise<void> {
  // Trigger a pre-configured Notification policy (webhook / PagerDuty)
  const resp = await fetch(
    `${NOTIF_BASE}/${accountId}/alerting/v3/test`,
    {
      method: 'POST',
      headers: {
        Authorization:  `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        policy_id: policyId,
        data: { message },
      }),
    }
  );
  if (!resp.ok) {
    console.error('Notification dispatch failed', resp.status, await resp.text());
  }
}
```

## Cron Trigger Worker — Full Assembly

```typescript
// src/index.ts
import { computeBurnRate } from './ae-burn-rate';
import { evaluateBurnRate } from './burn-rate-check';
import { sendAlert }        from './notify';

interface Env {
  CF_ACCOUNT_ID:        string;
  CF_API_TOKEN:         string;
  NOTIF_POLICY_PAGE:    string;  // Notification policy UUID for paging
  NOTIF_POLICY_TICKET:  string;  // Notification policy UUID for tickets
  LAST_ALERT:           KVNamespace; // dedup: store last fired severity+timestamp
}

export default {
  async scheduled(_ctrl: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    const burnRate = await computeBurnRate(env.CF_ACCOUNT_ID, env.CF_API_TOKEN);
    const severity = evaluateBurnRate(burnRate);

    if (severity === 'none') return;

    // Dedup: suppress if the same severity fired in the last 30 min
    const key = `last_alert:${severity}`;
    const lastFired = await env.LAST_ALERT.get(key);
    if (lastFired && Date.now() - Number(lastFired) < 30 * 60 * 1_000) return;

    const msg =
      `SLO burn-rate alert [${severity.toUpperCase()}]: ` +
      `short=${burnRate.shortRate.toFixed(1)}x long=${burnRate.longRate.toFixed(1)}x — ` +
      `error rate ${(burnRate.shortErrorRate * 100).toFixed(3)}%`;

    const policyId = severity === 'page'
      ? env.NOTIF_POLICY_PAGE
      : env.NOTIF_POLICY_TICKET;

    ctx.waitUntil(Promise.all([
      sendAlert(env.CF_ACCOUNT_ID, env.CF_API_TOKEN, policyId, msg),
      env.LAST_ALERT.put(key, String(Date.now()), { expirationTtl: 7200 }),
    ]));

    console.log(JSON.stringify({ type: 'slo_alert', severity, ...burnRate }));
  },
} satisfies ExportedHandler<Env>;
```

```toml
# wrangler.toml
[triggers]
crons = ["* * * * *"]   # every minute — evaluates multi-window burn rate
```

## Anti-patterns
- Alerting on instantaneous error rate instead of burn rate — causes alert fatigue during transient spikes
- Using a single burn-rate window — misses slow, sustained degradations that exhaust the budget over hours
- Storing the API token in plaintext in wrangler.toml — use Workers Secrets
- Firing a new alert on every cron tick — always dedup with KV or Durable Objects to avoid duplicate pages

## Gotchas
- Analytics Engine SQL has a ~1-minute data lag; the short window minimum meaningful size is 5 minutes
- The Cloudflare Notifications API `/alerting/v3/test` endpoint fires one-off alerts outside of normal alerting policies; use it carefully in production rate-limited by KV dedup
- `INTERVAL` arithmetic in AE SQL uses single-quoted strings: `INTERVAL '5' MINUTE` not `INTERVAL 5 MINUTE`
- Error budget burn rate is relative to the error budget, not the SLO target: `error_rate / (1 - SLO_target)`

## Verification
1. Deliberately return HTTP 500 from a test Worker endpoint at a rate exceeding the burn threshold
2. Verify the cron fires within 1 minute and the alert appears in the configured Notification destination
3. Confirm the KV dedup key suppresses duplicate pages for 30 minutes
4. Query AE SQL manually: `SELECT countIf(blob3='error')/count() FROM worker_requests WHERE timestamp > now() - INTERVAL '5' MINUTE`

## Related
- [slo-alerting-burn-rate.md](slo-alerting-burn-rate.md)
- [multiwindow-burn-rate-slo-alerts.md](multiwindow-burn-rate-slo-alerts.md)
- [cloudflare-analytics-engine.md](cloudflare-analytics-engine.md)
- [cloudflare-notifications-pagerduty-webhook.md](cloudflare-notifications-pagerduty-webhook.md)
- [sli-slo-error-budget-d1-tracking.md](sli-slo-error-budget-d1-tracking.md)

## Sources
- https://sre.google/workbook/alerting-on-slos/
- https://developers.cloudflare.com/fundamentals/notifications/create-notifications/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
