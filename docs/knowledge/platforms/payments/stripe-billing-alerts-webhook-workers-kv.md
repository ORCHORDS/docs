# Stripe Billing Alerts with Webhook Delivery to Workers and KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your SaaS tracks metered usage and charges via Stripe Billing. You need to alert customers when they have consumed a specified percentage of their included usage or crossed a spending threshold — proactively, before the invoice closes — so they can upgrade, control costs, or prepare for an overage charge. You also need internal ops alerts when any customer's monthly spend exceeds a business-defined limit, and you need deduplication so a customer at 80% usage does not receive the same alert every time a new meter event arrives.

## Context

Stripe's native `billing.alert` object (GA since 2024) lets you define thresholds on meter usage. When a threshold is crossed Stripe fires a `billing.alert.triggered` webhook event, once per alert per billing period. You handle this event in a Cloudflare Worker: look up the customer's notification preferences from KV, check a KV deduplication key so the alert fires once even if the webhook is retried, enqueue a message to a Queue for email/Slack dispatch, and optionally write to D1 for audit history. For internal ops alerts not modelled by Stripe (e.g., revenue-based thresholds), a Cron Trigger polls aggregated D1 invoice data nightly.

---

## 1. Creating Billing Alerts in Stripe

```typescript
// src/setup-alerts.ts — run once per product configuration, not per customer
import Stripe from 'stripe';

export async function provisionBillingAlerts(stripe: Stripe, meterId: string): Promise<void> {
  // Alert at 80% of included units
  await stripe.billing.alerts.create({
    title: '80% usage threshold',
    alert_type: 'usage_threshold',
    usage_threshold: {
      gte: 80,                       // percentage — Stripe interprets as >= 80%
      meter: meterId,
      recurrence: 'one_time',        // fire once per billing period
    },
  });

  // Alert at 100% (overage starts)
  await stripe.billing.alerts.create({
    title: '100% usage threshold — overage begins',
    alert_type: 'usage_threshold',
    usage_threshold: {
      gte: 100,
      meter: meterId,
      recurrence: 'one_time',
    },
  });
}
```

## 2. KV Schema for Notification Preferences and Deduplication

```typescript
// Key conventions (all values are JSON)
//
// Notification preferences:
//   key:  `notif_prefs:${customerId}`
//   value: NotifPrefs
//
// Deduplication (per alert per billing period):
//   key:  `alert_sent:${alertId}:${customerId}:${billingPeriodStart}`
//   value: '1'
//   TTL:  35 days (covers full billing period + 5-day buffer)

interface NotifPrefs {
  email: string;
  slackWebhookUrl?: string;
  emailEnabled: boolean;
  slackEnabled: boolean;
  thresholds: number[];   // [80, 100] — customer-chosen subset
}
```

## 3. Webhook Handler: `billing.alert.triggered`

```typescript
// src/webhooks/billing-alert.ts
import Stripe from 'stripe';
import { Env } from '../types';

export async function handleBillingAlertTriggered(
  event: Stripe.BillingAlertTriggeredEvent,
  env: Env
): Promise<void> {
  const alert = event.data.object;
  const customerId = alert.customer as string;
  const alertId = alert.alert.id;
  const threshold = alert.alert.usage_threshold?.gte ?? 0;

  // 1. Deduplication — Stripe may retry the webhook
  const dedupKey = `alert_sent:${alertId}:${customerId}:${alert.value}`;
  const alreadySent = await env.KV.get(dedupKey);
  if (alreadySent) return; // idempotent exit

  // Mark before dispatching to handle crash-recovery (at-least-once)
  await env.KV.put(dedupKey, '1', { expirationTtl: 35 * 86400 });

  // 2. Load notification preferences
  const prefs = await env.KV.get<NotifPrefs>(
    `notif_prefs:${customerId}`,
    { type: 'json' }
  );
  if (!prefs) return; // customer opted out of all alerts

  if (!prefs.thresholds.includes(threshold)) return; // customer filters this tier

  // 3. Enqueue for async delivery
  await env.ALERT_QUEUE.send({
    type: 'billing_alert',
    customerId,
    alertId,
    threshold,
    email: prefs.email,
    slackWebhookUrl: prefs.slackWebhookUrl,
    emailEnabled: prefs.emailEnabled,
    slackEnabled: prefs.slackEnabled,
    currentUsage: alert.value,
    triggeredAt: Math.floor(Date.now() / 1000),
  });

  // 4. Audit trail in D1
  await env.DB.prepare(
    `INSERT INTO billing_alert_log (alert_id, customer_id, threshold, current_value, sent_at)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(alertId, customerId, threshold, alert.value, Math.floor(Date.now() / 1000)).run();
}
```

## 4. Queue Consumer: Email and Slack Dispatch

```typescript
// src/queues/alert-consumer.ts
import { Env } from '../types';

interface AlertMessage {
  type: 'billing_alert';
  customerId: string;
  threshold: number;
  currentUsage: number;
  email: string;
  emailEnabled: boolean;
  slackWebhookUrl?: string;
  slackEnabled: boolean;
}

export default {
  async queue(batch: MessageBatch<AlertMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { body } = msg;

      if (body.emailEnabled) {
        await sendEmail(body.email, body.threshold, body.currentUsage, env);
      }

      if (body.slackEnabled && body.slackWebhookUrl) {
        await sendSlack(body.slackWebhookUrl, body.threshold, body.currentUsage);
      }

      msg.ack();
    }
  },
};

async function sendEmail(
  to: string,
  threshold: number,
  usage: number,
  env: Env
): Promise<void> {
  await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: 'billing@example.com', name: 'Example Billing' },
      subject: `You have used ${threshold}% of your plan`,
      content: [{
        type: 'text/plain',
        value: `Your account has reached ${usage.toLocaleString()} units (${threshold}% of your included plan). `
          + `Visit your billing portal to upgrade or manage usage.`,
      }],
    }),
  });
}

async function sendSlack(webhookUrl: string, threshold: number, usage: number): Promise<void> {
  await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `:warning: Billing alert: *${threshold}% of plan consumed* (${usage.toLocaleString()} units)`,
    }),
  });
}
```

## 5. Cron Trigger: Internal Ops Alert for Revenue Thresholds

```typescript
// src/scheduled/ops-alert.ts — fires nightly at 06:00 UTC
export async function checkRevenueThresholds(env: Env): Promise<void> {
  const OPS_THRESHOLD_CENTS = 10_000_00; // $10,000 MRR per customer triggers ops review

  const rows = await env.DB.prepare(
    `SELECT donor_id AS customer_id, SUM(amount_cents) AS total
     FROM donation_payments
     WHERE paid_at > strftime('%s','now','-30 days')
     GROUP BY donor_id
     HAVING total >= ?`
  ).bind(OPS_THRESHOLD_CENTS).all<{ customer_id: string; total: number }>();

  for (const row of rows.results) {
    const key = `ops_alert:revenue:${row.customer_id}:${monthBucket()}`;
    if (await env.KV.get(key)) continue; // already alerted this month
    await env.KV.put(key, '1', { expirationTtl: 35 * 86400 });

    await env.ALERT_QUEUE.send({
      type: 'ops_revenue_alert',
      customerId: row.customer_id,
      totalCents: row.total,
    });
  }
}

function monthBucket(): string {
  return new Date().toISOString().slice(0, 7); // 'YYYY-MM'
}
```

---

## Anti-patterns

- **Relying solely on Stripe's `one_time` recurrence without KV deduplication** — Stripe may deliver the webhook more than once on retry. Always guard with a deduplication key.
- **Sending the alert synchronously inside the webhook handler** — email and Slack dispatch can timeout (Workers have a 30-second CPU limit per invocation). Always enqueue to a Queue.
- **Creating a separate `billing.alert` object per customer** — Stripe billing alerts are global thresholds, not per-customer. One alert at 80% applies to all subscribers on the meter. Customer-specific preferences live in your KV, not in Stripe.
- **Not setting a TTL on dedup keys** — KV has a 25 GB namespace limit. Dedup keys without a TTL accumulate indefinitely.

## Gotchas

- The `billing.alert.triggered` event's `alert.value` is the raw meter event count, not the percentage. The percentage is determined by comparing against the subscription's included quantity: `percentage = (value / includedQuantity) * 100`. You must look up the included quantity from the subscription's price tier.
- Stripe billing alerts fire once per `recurrence` per billing period, resetting when a new billing period begins. If you want alerts on each additional 10% interval, create separate alert objects (80%, 90%, 100%).
- `recurrence: 'one_time'` is the only option as of API version 2024-06-20; a `'recurring'` option (re-fires each usage increment) is on Stripe's roadmap.
- Cloudflare Queues have a maximum message size of 128 KB. Billing alert payloads are tiny, but if you embed rendered HTML email bodies, keep them server-side.

## Verification

```bash
# List your billing alerts
stripe billing alerts list

# Simulate trigger in Stripe test mode
stripe trigger billing.alert.triggered

# Check dedup KV key was set
wrangler kv key get "alert_sent:balt_xxx:cus_xxx:8000" \
  --namespace-id your-namespace-id

# Check D1 audit log
wrangler d1 execute YOUR_DB \
  --command "SELECT * FROM billing_alert_log ORDER BY sent_at DESC LIMIT 10"
```

## Related

- `stripe-billing-meter-workers-ingestion-pipeline.md`
- `stripe-metered-billing.md`
- `stripe-usage-based-billing.md`
- `payment-retry-exponential-backoff-cloudflare-queues.md`
- `stripe-webhook-idempotency-d1-event-log.md`

## Sources

- https://docs.stripe.com/billing/alerts
- https://docs.stripe.com/api/billing/alert
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
