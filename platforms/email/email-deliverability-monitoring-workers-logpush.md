# Email Deliverability Monitoring with Workers and Logpush

- Date: 2026-08-22
- Author: example.com
- Status: production

## Continuous Deliverability Health Monitoring

Email deliverability degrades silently. Bounce rates climb, spam complaints
accumulate, and IP reputation erodes long before any dashboard alert fires. By
the time a human notices, a domain may already be blocklisted. Teams need
automated, continuous monitoring that polls ESP webhook stats, persists raw
event streams for trend analysis, and pushes alerts the moment reputation
metrics cross defined thresholds.

Cloudflare Workers Cron Triggers are a natural fit: they run on a schedule
with no infrastructure to maintain, can call ESP APIs directly, write
structured event rows to Analytics Engine, and fan out to Cloudflare
Notifications or a webhook on degradation. Logpush exports the same
Analytics Engine data to R2 so queries spanning weeks or months remain fast
without hitting row limits.

The result is a full observability loop — send → track → alert → investigate
— that runs entirely on the Cloudflare platform without a separate monitoring
service.

## Context

Stack: Cloudflare Workers (Cron Trigger), Analytics Engine, R2, Logpush,
Cloudflare Notifications (Webhooks), SendGrid Event Webhook or Resend
Webhooks, Wrangler 3+, TypeScript.

The Worker runs on a five-minute schedule. A separate inbound webhook Worker
receives real-time ESP event pushes and writes them to Analytics Engine. The
cron job aggregates those blobs, computes derived metrics (bounce rate, spam
rate, delivery rate), and compares them against configurable thresholds stored
in a KV namespace.

## ESP Webhook Ingestion Worker

Receive real-time events from SendGrid or Resend and write each one as a
measurement to Analytics Engine.

```ts
// workers/esp-event-ingestion.ts
interface Env {
  EMAIL_EVENTS: AnalyticsEngineDataset;
  ESP_WEBHOOK_SECRET: string;
}

interface ESPEvent {
  event: 'delivered' | 'bounce' | 'spamreport' | 'deferred' | 'open' | 'click';
  email: string;
  timestamp: number;
  sg_message_id?: string;
  reason?: string;
  ip?: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Validate SendGrid signature
    const sig = req.headers.get('X-Twilio-Email-Event-Webhook-Signature') ?? '';
    if (!sig) return new Response('Forbidden', { status: 403 });

    const body = await req.json<ESPEvent[]>();

    for (const evt of body) {
      env.EMAIL_EVENTS.writeDataPoint({
        blobs: [evt.event, evt.email, evt.reason ?? '', evt.ip ?? ''],
        doubles: [evt.timestamp, 1],
        indexes: [evt.event],
      });
    }

    return new Response('ok');
  },
};
```

## Cron Aggregation and Alerting Worker

Every five minutes, query Analytics Engine for a rolling one-hour window,
compute reputation metrics, and fire an alert if any threshold is breached.

```ts
// workers/deliverability-monitor.ts
interface Env {
  EMAIL_EVENTS: AnalyticsEngineDataset;
  THRESHOLDS: KVNamespace;
  ALERT_WEBHOOK_URL: string;
  CLOUDFLARE_ACCOUNT_ID: string;
  AE_API_TOKEN: string;
}

async function queryAE(env: Env, sql: string): Promise<Record<string, number>> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CLOUDFLARE_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.AE_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  const { data } = await res.json<{ data: Record<string, number>[] }>();
  return data[0] ?? {};
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const window = `timestamp > now() - INTERVAL '1' HOUR`;

    const row = await queryAE(
      env,
      `SELECT
         countIf(blob1 = 'delivered')   AS delivered,
         countIf(blob1 = 'bounce')      AS bounced,
         countIf(blob1 = 'spamreport') AS spam,
         count()                        AS total
       FROM EMAIL_EVENTS
       WHERE ${window}`
    );

    const total = row.total || 1;
    const bounceRate = row.bounced / total;
    const spamRate = row.spam / total;

    const thresholds = JSON.parse(
      (await env.THRESHOLDS.get('email_thresholds')) ??
        '{"bounce":0.05,"spam":0.001}'
    );

    const alerts: string[] = [];
    if (bounceRate > thresholds.bounce)
      alerts.push(`Bounce rate ${(bounceRate * 100).toFixed(2)}% > ${thresholds.bounce * 100}%`);
    if (spamRate > thresholds.spam)
      alerts.push(`Spam rate ${(spamRate * 100).toFixed(3)}% > ${thresholds.spam * 100}%`);

    if (alerts.length > 0) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `Email deliverability alert:\n${alerts.join('\n')}`,
          metrics: { bounceRate, spamRate, total },
          ts: Date.now(),
        }),
      });
    }
  },
};
```

## Logpush Export for Trend Analysis

Configure Logpush to ship Analytics Engine blobs to R2 daily. Use `wrangler`
or the Cloudflare dashboard.

```ts
// scripts/configure-logpush.ts  (run once via wrangler execute)
const payload = {
  name: 'email-events-to-r2',
  destination_conf: `r2://<BUCKET>/email-events/{DATE}?account-id=<ACCOUNT>`,
  dataset: 'workers_analytics_engine',
  logpull_options: 'fields=Timestamp,Blob1,Blob2,Blob3,Double1&timestamps=rfc3339',
  filter: JSON.stringify({ key: 'Dataset', operator: 'eq', value: 'EMAIL_EVENTS' }),
  frequency: 'high',
};

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs`,
  {
    method: 'POST',
    headers: { Authorization: `Bearer ${API_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
);
console.log(await res.json());
```

R2 objects land under `email-events/2026-08-22/` as newline-delimited JSON,
queryable via Workers R2 bindings or external tooling.

## Anti-patterns

- Polling ESP REST APIs on every cron tick instead of receiving push events; webhook ingestion is far lower latency and cheaper
- Storing raw events in KV — KV is not queryable; Analytics Engine is purpose-built for this
- Setting thresholds too tight (bounce > 0.5%) causing alert fatigue; calibrate against your list quality baseline first
- Forgetting to validate ESP webhook signatures — any caller could inject fake events

## Gotchas

- Analytics Engine SQL via REST API has a 1 000-row result cap per query; use aggregations, not row scans
- Logpush jobs export on a delay (up to 5 minutes for `high` frequency); real-time alerting must come from the cron job, not Logpush
- SendGrid's webhook signature uses ECDSA; verify with the `X-Twilio-Email-Event-Webhook-Signature` and `X-Twilio-Email-Event-Webhook-Timestamp` headers together
- Resend webhooks use `svix-signature`; validate with the Svix SDK before processing

## Verification

```ts
// Confirm events are flowing — run in wrangler tail or via AE SQL
const sql = `SELECT blob1 AS event, count() AS n
             FROM EMAIL_EVENTS
             WHERE timestamp > now() - INTERVAL '10' MINUTE
             GROUP BY blob1
             ORDER BY n DESC`;
// Expected: rows for 'delivered', 'bounce', etc. with non-zero counts
```

## Related

- analytics-engine-email-tracking.md
- complaint-rate-monitoring.md
- sendgrid-resend-cloudflare-workers-integration.md
- bounce-handling-hard-soft.md
- cloudflare-email-routing-workers.md

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/logs/get-started/enable-destinations/r2/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://docs.sendgrid.com/for-developers/tracking-events/event
- https://resend.com/docs/dashboard/webhooks/introduction
