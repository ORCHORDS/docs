# Email Complaint Rate Monitoring with Cloudflare Workers and Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

ESP dashboards show complaint rates only in aggregate and with 24-hour lag. You need per-campaign, per-domain, and per-list-segment complaint rates in near-real-time so you can suppress senders or pause campaigns before Gmail or Yahoo bulk-sender thresholds (0.10% warning / 0.30% block) are breached.

---

## Context

Gmail Postmaster Tools and Yahoo Feedback Loop both POST FBL events via webhook or SMTP bounce-like messages. Cloudflare Workers receive these, normalize them, write to Analytics Engine (write-optimized columnar store, sub-second ingestion), and serve dashboard queries via SQL over HTTP. D1 holds the suppression list that the monitoring pipeline feeds automatically.

---

## Inbound FBL Webhook Handler

```typescript
// src/fbl-webhook.ts
import { Env } from './types';

interface FblEvent {
  messageId: string;
  reportingMta: string;    // e.g. "gmail.com"
  originalRecipient: string;
  feedbackType: 'abuse' | 'fraud' | 'other';
  campaignId?: string;
  listId?: string;
  timestamp: number;       // epoch seconds
}

export async function handleFblWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  // Validate shared secret
  const sig = request.headers.get('X-FBL-Signature');
  if (sig !== env.FBL_SECRET) return new Response('Unauthorized', { status: 401 });

  const event = await request.json<FblEvent>();

  // Write to Analytics Engine — non-blocking
  env.COMPLAINT_AE.writeDataPoint({
    blobs: [
      event.messageId,
      event.reportingMta,
      event.originalRecipient,
      event.campaignId ?? 'unknown',
      event.listId ?? 'unknown',
      event.feedbackType,
    ],
    doubles: [1],                         // count, always 1 per event
    indexes: [event.campaignId ?? 'none'],// allows fast per-campaign filter
    timestamp: new Date(event.timestamp * 1000),
  });

  // Immediately add to suppression list in D1
  await suppressRecipient(env, event.originalRecipient, event.reportingMta);

  return new Response('OK', { status: 200 });
}

async function suppressRecipient(
  env: Env,
  email: string,
  source: string
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO suppression_list (email, reason, source, created_at)
    VALUES (?, 'complaint', ?, ?)
    ON CONFLICT (email) DO UPDATE SET
      reason = 'complaint',
      source = excluded.source,
      updated_at = excluded.created_at
  `).bind(email.toLowerCase(), source, Date.now()).run();
}
```

---

## Analytics Engine Dataset Binding (wrangler.toml)

```toml
[[analytics_engine_datasets]]
binding = "COMPLAINT_AE"
dataset = "email_complaints"
```

Schema (blobs / doubles map):
| Index | Field |
|---|---|
| blobs[0] | message_id |
| blobs[1] | reporting_mta |
| blobs[2] | recipient (hashed at query time) |
| blobs[3] | campaign_id |
| blobs[4] | list_id |
| blobs[5] | feedback_type |
| doubles[0] | count (1) |

---

## Real-time Complaint Rate Calculation

```typescript
// src/complaint-rate.ts — queries Analytics Engine SQL API
const AE_SQL_URL =
  `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}` +
  `/analytics_engine/sql`;

export interface ComplaintRateRow {
  campaign_id: string;
  complaints: number;
  complaint_rate: number;   // fraction, e.g. 0.0012 = 0.12%
  window_hours: number;
}

export async function getComplaintRates(
  env: Env,
  windowHours = 24
): Promise<ComplaintRateRow[]> {
  const query = `
    SELECT
      blob4                             AS campaign_id,
      SUM(_sample_interval * double1)   AS complaints,
      SUM(_sample_interval * double1) /
        NULLIF(
          (SELECT SUM(_sample_interval * double1)
           FROM email_sends
           WHERE blob4 = c.blob4
             AND timestamp > NOW() - INTERVAL '${windowHours}' HOUR),
          0
        )                               AS complaint_rate
    FROM email_complaints c
    WHERE timestamp > NOW() - INTERVAL '${windowHours}' HOUR
    GROUP BY blob4
    ORDER BY complaint_rate DESC
  `;

  const res = await fetch(AE_SQL_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
  });

  const json = await res.json<{ data: ComplaintRateRow[] }>();
  return json.data.map(r => ({ ...r, window_hours: windowHours }));
}
```

---

## Threshold Alerting Worker

```typescript
// src/alerting.ts — scheduled cron every 15 minutes
const WARN_THRESHOLD  = 0.001;   // 0.10% — Google warning level
const BLOCK_THRESHOLD = 0.003;   // 0.30% — Google block level

export async function checkThresholds(env: Env): Promise<void> {
  const rates = await getComplaintRates(env, 24);

  for (const row of rates) {
    if (row.complaint_rate >= BLOCK_THRESHOLD) {
      await pauseCampaign(env, row.campaign_id, 'block_threshold');
      await sendAlert(env, row, 'CRITICAL');
    } else if (row.complaint_rate >= WARN_THRESHOLD) {
      await sendAlert(env, row, 'WARNING');
    }
  }
}

async function pauseCampaign(
  env: Env,
  campaignId: string,
  reason: string
): Promise<void> {
  await env.DB.prepare(`
    UPDATE campaigns SET status = 'paused', pause_reason = ?, paused_at = ?
    WHERE id = ? AND status = 'active'
  `).bind(reason, Date.now(), campaignId).run();
}

async function sendAlert(
  env: Env,
  row: ComplaintRateRow,
  level: 'WARNING' | 'CRITICAL'
): Promise<void> {
  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `[${level}] Campaign ${row.campaign_id} complaint rate: ` +
            `${(row.complaint_rate * 100).toFixed(3)}% ` +
            `(${row.complaints} complaints / ${row.window_hours}h window)`,
    }),
  });
}
```

---

## Per-domain Breakdown Query

```typescript
// Useful for diagnosing whether a complaint spike is Gmail-specific vs Yahoo-specific
export async function getComplaintsByDomain(
  env: Env,
  campaignId: string
): Promise<{ domain: string; complaints: number }[]> {
  const query = `
    SELECT
      blob2                           AS domain,
      SUM(_sample_interval * double1) AS complaints
    FROM email_complaints
    WHERE blob4 = '${campaignId}'
      AND timestamp > NOW() - INTERVAL '48' HOUR
    GROUP BY blob2
    ORDER BY complaints DESC
  `;

  const res = await fetch(AE_SQL_URL, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query }),
  });

  const json = await res.json<{ data: { domain: string; complaints: number }[] }>();
  return json.data;
}
```

---

## Suppression List D1 Schema

```sql
CREATE TABLE suppression_list (
  email       TEXT PRIMARY KEY,
  reason      TEXT NOT NULL,   -- 'complaint' | 'bounce' | 'manual'
  source      TEXT,            -- reporting MTA
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER
);

CREATE TABLE campaigns (
  id           TEXT PRIMARY KEY,
  status       TEXT NOT NULL DEFAULT 'active',
  pause_reason TEXT,
  paused_at    INTEGER
);
```

---

## Anti-patterns

- **Storing raw complaint events in D1** — D1 write throughput is limited; Analytics Engine handles millions of data points per second without contention.
- **Querying complaint rate from send logs alone** — send count must come from an `email_sends` AE dataset, not a D1 table scan, or the division denominator will be inconsistent.
- **Alerting on absolute complaint count** — a large campaign with 10 000 recipients and 8 complaints (0.08%) is healthy; a small campaign with 200 recipients and 2 complaints (1.0%) is critical.
- **Only checking Gmail FBL** — Yahoo, AOL, and Comcast all offer FBLs; ignoring them leaves blind spots on those MTA domains.

---

## Gotchas

- Analytics Engine data points are sampled at high volumes; always use `SUM(_sample_interval * double1)` rather than `COUNT(*)` to get accurate totals.
- Google Postmaster Tools complaint data is aggregate by domain, not per-message; use Gmail FBL (requires Google approval) for individual message IDs.
- The AE SQL API enforces a 1-minute result cache; for alerting, accept the cache lag and schedule crons at least 2 minutes apart.
- Yahoo FBL sends actual bounced copies of the original message to a designated mailbox — use Cloudflare Email Routing to pipe these to a Worker for parsing.

---

## Verification

```bash
# Simulate a complaint event
curl -X POST https://workers.example.com/fbl \
  -H "X-FBL-Signature: ${FBL_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{
    "messageId":"<abc@msg.example.com>",
    "reportingMta":"gmail.com",
    "originalRecipient":"victim@gmail.com",
    "feedbackType":"abuse",
    "campaignId":"campaign_42",
    "listId":"list_7",
    "timestamp":1761264000
  }'

# Query AE for complaint rate
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"query":"SELECT blob4, SUM(_sample_interval * double1) AS complaints FROM email_complaints WHERE timestamp > NOW() - INTERVAL '\''1'' HOUR GROUP BY blob4"}'

# Confirm suppression
wrangler d1 execute DB --command \
  "SELECT * FROM suppression_list WHERE email='victim@gmail.com'"
```

---

## Related

- `complaint-rate-monitoring.md`
- `email-deliverability-feedback-loop-isp-workers.md`
- `analytics-engine-email-tracking.md`
- `email-suppression-list-kv-workers.md`
- `email-bounce-storm-circuit-breaker-workers.md`
- `gmail-yahoo-bulk-sender-requirements.md`

---

## Sources

- Google Feedback Loop: https://support.google.com/mail/answer/6254652
- Yahoo Complaint Feedback Loop: https://senders.yahooinc.com/complaint-feedback-loop/
- Cloudflare Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Gmail bulk sender thresholds: https://support.google.com/mail/answer/81126
