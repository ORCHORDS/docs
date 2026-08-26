# Email Deliverability Score Tracking in Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Teams sending transactional and marketing email need a single numeric health
signal — a deliverability score — that aggregates bounce rate, spam complaint
rate, open rate, unsubscribe rate, and DMARC pass rate into one dashboard metric.
Without it, engineers monitor five separate charts and miss correlations between
signals before reputation damage occurs.

## Context

Cloudflare Analytics Engine accepts arbitrary event data from Workers and exposes
it via the Workers Analytics Engine SQL API. By writing one structured
`writeDataPoint()` call per email event (send, bounce, complaint, open, etc.) with
consistent index/blob fields, you can derive a composite deliverability score
using SQL aggregations on a 24-hour rolling window — no external analytics stack
required.

## Analytics Engine Dataset Design

| Field | Kind | Purpose |
|---|---|---|
| `index1` | string | sending domain (e.g. `mail.example.com`) |
| `blob1`  | string | event type: `send`, `bounce_hard`, `bounce_soft`, `complaint`, `open`, `click`, `unsubscribe`, `dmarc_pass`, `dmarc_fail` |
| `blob2`  | string | campaign or template ID |
| `blob3`  | string | ESP / sending IP pool |
| `double1` | number | 1.0 (count; allows SUM aggregation) |
| `double2` | number | event-specific weight (see scoring model) |

## Writing Events from Workers

```typescript
// analytics/events.ts
export type EmailEventType =
  | 'send'
  | 'bounce_hard'
  | 'bounce_soft'
  | 'complaint'
  | 'open'
  | 'click'
  | 'unsubscribe'
  | 'dmarc_pass'
  | 'dmarc_fail';

// Weights used in the composite score (positive = good, negative = bad)
const EVENT_WEIGHT: Record<EmailEventType, number> = {
  send:         0,
  bounce_hard: -5,
  bounce_soft: -1,
  complaint:   -10,
  open:         2,
  click:        3,
  unsubscribe: -2,
  dmarc_pass:   1,
  dmarc_fail:  -3,
};

export interface EmailEvent {
  domain: string;
  eventType: EmailEventType;
  campaignId?: string;
  espPool?: string;
}

export function recordEmailEvent(
  ae: AnalyticsEngineDataset,
  event: EmailEvent,
): void {
  ae.writeDataPoint({
    indexes: [event.domain],
    blobs: [
      event.eventType,
      event.campaignId ?? 'none',
      event.espPool ?? 'default',
    ],
    doubles: [
      1.0,
      EVENT_WEIGHT[event.eventType],
    ],
  });
}
```

Bind the dataset in `wrangler.jsonc`:

```jsonc
{
  "analytics_engine_datasets": [
    { "binding": "EMAIL_AE", "dataset": "email_deliverability" }
  ]
}
```

## Calling from Send / Webhook Workers

```typescript
// In your send Worker, after a successful dispatch:
recordEmailEvent(env.EMAIL_AE, {
  domain: 'mail.example.com',
  eventType: 'send',
  campaignId: job.campaignId,
});

// In your bounce webhook handler (e.g. SendGrid Event Webhook):
export async function processBounceWebhook(
  events: SendGridEvent[],
  env: Env,
): Promise<void> {
  for (const ev of events) {
    if (ev.event === 'bounce') {
      recordEmailEvent(env.EMAIL_AE, {
        domain: extractSendingDomain(ev.email),
        eventType: ev.type === 'bounce' ? 'bounce_hard' : 'bounce_soft',
        campaignId: ev['X-Campaign-ID'],
      });
    }
    if (ev.event === 'spamreport') {
      recordEmailEvent(env.EMAIL_AE, {
        domain: extractSendingDomain(ev.email),
        eventType: 'complaint',
        campaignId: ev['X-Campaign-ID'],
      });
    }
  }
}
```

## Querying the Composite Score

The Workers Analytics Engine SQL API endpoint:
`https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`

```sql
-- Deliverability score per domain, last 24 hours
-- Score = 100 + SUM(weight * count) / SUM(sends) * 100
-- Clipped to [0, 100]

SELECT
  index1                                      AS domain,
  SUM(double1)                                AS total_events,
  SUM(CASE WHEN blob1 = 'send' THEN double1 ELSE 0 END) AS sends,
  SUM(double2)                                AS raw_weight_sum,
  MIN(
    100,
    MAX(
      0,
      100 + (SUM(double2) / NULLIF(
        SUM(CASE WHEN blob1 = 'send' THEN double1 ELSE 0 END), 0
      )) * 100
    )
  )                                           AS deliverability_score
FROM email_deliverability
WHERE timestamp > NOW() - INTERVAL '1' DAY
GROUP BY index1
ORDER BY deliverability_score ASC;
```

## Dashboard Worker (JSON API)

```typescript
// score-api/index.ts
const AE_SQL = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const sql = `
      SELECT index1 AS domain,
             MIN(100, MAX(0, 100 + (SUM(double2) /
               NULLIF(SUM(CASE WHEN blob1='send' THEN double1 ELSE 0 END),0))*100))
               AS score
      FROM email_deliverability
      WHERE timestamp > NOW() - INTERVAL '1' DAY
      GROUP BY index1
      ORDER BY score ASC
    `;

    const res = await fetch(AE_SQL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    });

    const data = await res.json();
    return Response.json(data);
  },
};
```

## Score Interpretation

| Score | Status | Action |
|---|---|---|
| 90–100 | Healthy | Monitor weekly |
| 70–89 | Degraded | Review bounce classification; check complaint sources |
| 50–69 | At risk | Pause campaigns; investigate suppression gaps |
| < 50 | Critical | Stop sending; remediate before resuming |

## Anti-patterns

- **Averaging scores across campaigns** — dilutes the signal; always segment by
  sending domain and, secondarily, by campaign.
- **Omitting DMARC events** — DMARC failures are an early warning before
  deliverability degradation shows up in bounces; always instrument them.
- **Using Analytics Engine for individual recipient records** — AE is for
  aggregated metrics only; store PII-bearing per-recipient data in D1.
- **Polling the SQL API on every page load** — AE SQL queries have rate limits;
  cache the score in KV with a 5-minute TTL.

## Gotchas

- Analytics Engine data points are sampled when write volume is very high; for
  sub-1% sampling rates set `sampling_rate` in your dataset configuration.
- The SQL API `NOW()` function returns UTC; ensure your WHERE clause aligns with
  the timezone of any external dashboards you build.
- `double2` stores signed weights; SUM can return negative values for very bad
  batches — the `MAX(0, …)` guard in the query prevents negative scores.
- Analytics Engine has an eventual-consistency lag of ~30 seconds; real-time
  alerting on complaint spikes should use a separate D1 counter.

## Verification

```bash
# Write a test data point
curl -X POST https://score-api.example.com/

# Query raw data
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1, SUM(double1) FROM email_deliverability WHERE timestamp > NOW() - INTERVAL '"'"'1'"'"' HOUR GROUP BY blob1"}'
```

## Related

- `email-open-click-analytics-engine.md`
- `analytics-engine-email-tracking.md`
- `email-complaint-rate-monitoring-workers-analytics.md`
- `email-postmaster-api-workers-analytics-engine.md`
- `email-deliverability-monitoring-workers-logpush.md`

## Sources

- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- AE SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- AE writeDataPoint(): https://developers.cloudflare.com/analytics/analytics-engine/get-started/
