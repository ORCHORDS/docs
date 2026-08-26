# Cloudflare Notifications Webhook Workers Routing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project uses Cloudflare Notifications (Health Checks, Workers error rate spikes, DDoS alerts) to detect infrastructure issues, but the Cloudflare dashboard only supports a handful of notification destinations out of the box. The team needs to fan a single Cloudflare webhook notification out to multiple sinks — PagerDuty for on-call, Slack for the team channel, and Analytics Engine for incident correlation — without duplicating webhook URL configuration for each service. A routing Worker acts as an intelligent dispatcher, enriching each notification before forwarding.

## Context

Cloudflare Notifications support a generic webhook destination that sends an HTTP POST with a JSON payload signed with an HMAC-SHA256 signature. A Worker placed at the webhook URL receives these payloads before any downstream service, enabling deduplication, enrichment, routing logic, and guaranteed delivery via Queues. The signature verification ensures only Cloudflare can trigger the Worker, preventing spoofed alerts. Cloudflare notification types include Workers error rate, Health Check status change, DDoS L3/L4/L7, Tunnel health, and Zone analytics.

## Section 1 — Instrumentation: Signature Verification and Payload Parsing

All Cloudflare webhook notifications include a `cf-webhook-auth` header containing the HMAC-SHA256 hex digest of the raw request body, keyed with a secret set in the Cloudflare dashboard. Verify this before processing.

```typescript
// workers/src/notification-router/verify.ts

export async function verifyCloudflareWebhook(
  request: Request,
  secret: string
): Promise<{ valid: boolean; body: string }> {
  const signature = request.headers.get("cf-webhook-auth") ?? "";
  const body = await request.text();

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );

  const sigBytes = new Uint8Array(
    signature.match(/.{2}/g)!.map((b) => parseInt(b, 16))
  );
  const bodyBytes = new TextEncoder().encode(body);

  const valid = await crypto.subtle.verify("HMAC", key, sigBytes, bodyBytes);
  return { valid, body };
}

export interface CloudflareNotification {
  name: string;           // e.g. "Workers Error Rate Alert"
  text: string;           // human-readable description
  data: {
    alert_type: string;   // e.g. "workers_uptime"
    zones?: string[];
    sent: string;         // ISO timestamp

  };
}

export function parseNotification(body: string): CloudflareNotification | null {
  try {
    return JSON.parse(body) as CloudflareNotification;
  } catch {
    return null;
  }
}
```

## Section 2 — Routing Logic: Fan-Out to Multiple Destinations

Route each notification type to the appropriate downstream services. Use a priority map so critical alerts go to PagerDuty while informational alerts go only to Slack.

```typescript
// workers/src/notification-router/router.ts
import { CloudflareNotification } from "./verify";

export type Severity = "critical" | "warning" | "info";

export interface RoutingDecision {
  severity: Severity;
  destinations: Array<"pagerduty" | "slack" | "analytics_engine">;
  dedupKey: string;
}

const ALERT_TYPE_MAP: Record<string, { severity: Severity; pd: boolean }> = {
  workers_uptime:             { severity: "critical", pd: true },
  workers_error_rate_alert:   { severity: "critical", pd: true },
  ddos_layer_7_alert:         { severity: "critical", pd: true },
  ddos_layer_4_alert:         { severity: "critical", pd: true },
  health_check_status_change: { severity: "warning",  pd: false },
  tunnel_health_event:        { severity: "warning",  pd: false },
  billing_usage_alert:        { severity: "info",     pd: false },
};

export function routeNotification(notif: CloudflareNotification): RoutingDecision {
  const alertType = notif.data.alert_type ?? "unknown";
  const config = ALERT_TYPE_MAP[alertType] ?? { severity: "info" as Severity, pd: false };

  const destinations: RoutingDecision["destinations"] = ["analytics_engine", "slack"];
  if (config.pd) destinations.unshift("pagerduty");

  return {
    severity: config.severity,
    destinations,
    dedupKey: `cf-${alertType}-${notif.data.sent}`,
  };
}

export async function forwardToPagerDuty(
  notif: CloudflareNotification,
  decision: RoutingDecision,
  pdRoutingKey: string
): Promise<void> {
  await fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      routing_key: pdRoutingKey,
      event_action: "trigger",
      dedup_key: decision.dedupKey,
      payload: {
        summary: notif.name,
        severity: decision.severity === "critical" ? "critical" : "warning",
        source: "cloudflare-notifications",
        timestamp: notif.data.sent,
        custom_details: notif.data,
      },
    }),
  });
}

export async function forwardToSlack(
  notif: CloudflareNotification,
  decision: RoutingDecision,
  slackWebhookUrl: string
): Promise<void> {
  const icon = decision.severity === "critical" ? ":rotating_light:" : ":warning:";
  await fetch(slackWebhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `${icon} *${notif.name}*\n${notif.text}`,
      attachments: [
        {
          color: decision.severity === "critical" ? "danger" : "warning",
          fields: Object.entries(notif.data)
            .filter(([k]) => !["sent", "alert_type"].includes(k))
            .slice(0, 5)
            .map(([title, value]) => ({
              title,
              value: String(value).slice(0, 200),
              short: true,
            })),
        },
      ],
    }),
  });
}
```

## Section 3 — Worker Entry Point with Queue-Backed Guaranteed Delivery

Use Cloudflare Queues as a buffer to guarantee delivery even if a downstream service (Slack, PagerDuty) is temporarily unavailable. The router Worker enqueues immediately; a consumer Worker handles retries.

```typescript
// workers/src/notification-router/index.ts
import { verifyCloudflareWebhook, parseNotification } from "./verify";
import { routeNotification, forwardToPagerDuty, forwardToSlack } from "./router";

interface Env {
  WEBHOOK_SECRET: string;
  NOTIFICATION_QUEUE: Queue<string>;
  ANALYTICS_ENGINE: AnalyticsEngineDataset;
  ENVIRONMENT: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { valid, body } = await verifyCloudflareWebhook(request, env.WEBHOOK_SECRET);
    if (!valid) return new Response("Unauthorized", { status: 401 });

    // Enqueue for reliable processing — respond 200 immediately to Cloudflare
    ctx.waitUntil(env.NOTIFICATION_QUEUE.send(body));

    return new Response("Accepted", { status: 202 });
  },
};

// Consumer Worker — separate script or same script with queue handler
export const queueConsumer = {
  async queue(batch: MessageBatch<string>, env: Env & {
    PD_ROUTING_KEY: string;
    SLACK_WEBHOOK_URL: string;
  }): Promise<void> {
    for (const msg of batch.messages) {
      const notif = parseNotification(msg.body);
      if (!notif) { msg.ack(); continue; }

      const decision = routeNotification(notif);

      // Write to Analytics Engine regardless of downstream fate
      env.ANALYTICS_ENGINE.writeDataPoint({
        blobs: [
          "cf_notification",
          notif.data.alert_type ?? "unknown",
          decision.severity,
          env.ENVIRONMENT,
        ],
        doubles: [Date.now()],
        indexes: [decision.dedupKey.slice(0, 32)],
      });

      const tasks = decision.destinations
        .filter((d) => d !== "analytics_engine")
        .map((dest) =>
          dest === "pagerduty"
            ? forwardToPagerDuty(notif, decision, env.PD_ROUTING_KEY)
            : forwardToSlack(notif, decision, env.SLACK_WEBHOOK_URL)
        );

      try {
        await Promise.all(tasks);
        msg.ack();
      } catch (err) {
        console.error("Notification forward failed, will retry:", err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};
```

## Section 4 — Analytics Engine Notification History Dashboard

```sql
-- Notification volume by type and severity (last 30 days)
SELECT
  blob2 AS alert_type,
  blob3 AS severity,
  COUNT(*) AS count,
  DATE_TRUNC('day', timestamp) AS day
FROM analytics_engine_dataset
WHERE blob1 = 'cf_notification'
  AND timestamp > NOW() - INTERVAL '30' DAY
GROUP BY 1, 2, 4
ORDER BY 4 DESC, 3 DESC;

-- Critical alert frequency (hourly, last 7 days) for burn rate context
SELECT
  DATE_TRUNC('hour', timestamp) AS hour,
  COUNT(*) AS critical_alerts
FROM analytics_engine_dataset
WHERE blob1 = 'cf_notification'
  AND blob3 = 'critical'
  AND timestamp > NOW() - INTERVAL '7' DAY
GROUP BY 1
ORDER BY 1;

-- Recent notifications (latest 20)
SELECT
  timestamp,
  blob2 AS alert_type,
  blob3 AS severity,
  index1 AS dedup_key
FROM analytics_engine_dataset
WHERE blob1 = 'cf_notification'
ORDER BY timestamp DESC
LIMIT 20;
```

## Anti-patterns

- Responding 200 to Cloudflare only after all forwarding completes — if Slack is slow, Cloudflare may retry and you get duplicate notifications; always respond 202 immediately and process asynchronously.
- Skipping HMAC verification to "simplify" the Worker — any HTTP client can spoof alerts and trigger false PagerDuty incidents.
- Forwarding `notif.text` verbatim to PagerDuty `summary` — the text field can be long and PagerDuty truncates at 1 024 characters; use `notif.name` as summary and push detail to `custom_details`.
- Routing all notification types to PagerDuty — billing alerts and health check flaps will create alert fatigue; use the severity map to gate PD escalation.
- Using a single Queue for all environments — staging notifications will wake on-call engineers; use separate bindings per environment.

## Gotchas

- Cloudflare retries webhook deliveries if it receives a non-2xx response or a timeout; the Queue buffer absorbs retries safely since the consumer is idempotent on `dedupKey`.
- The `cf-webhook-auth` header value is a lowercase hex string without a `sha256=` prefix; do not strip any prefix before converting to bytes.
- Queue `retry({ delaySeconds })` is capped at 86 400 seconds (24 hours); alerts older than this will not be retried.
- Cloudflare Notifications webhooks do not include a `zone_id` in all payloads — `notif.data.zones` may be an array or undefined depending on alert type.
- The Analytics Engine data point for each notification is written before forwarding; this means even failed deliveries are recorded in the audit trail.

## Verification

1. Set `WEBHOOK_SECRET` in Wrangler secrets.
2. Compute expected HMAC: `echo -n '{"name":"test"}' | openssl dgst -sha256 -hmac "$SECRET" -hex`.
3. Send a POST to the Worker URL with the computed signature in `cf-webhook-auth`.
4. Confirm the Queue consumer logs "Notification forward failed, will retry" when Slack URL is invalid, and the message appears in the Queue's retry backlog.
5. With valid downstream URLs, confirm PagerDuty incident creation for a `workers_uptime` payload and Slack message for a `health_check_status_change` payload.

## Related

- `/documentation/docs/policies/monitoring/cloudflare-notifications-pagerduty-webhook.md`
- `/documentation/docs/policies/monitoring/cloudflare-notifications-slack-webhook-workers.md`
- `/documentation/docs/policies/monitoring/workers-error-alerting-pagerduty-integration.md`
- `/documentation/docs/policies/monitoring/cloudflare-queues-async-tracing.md`
- `/documentation/docs/policies/monitoring/incident-runbook-workers-status-page-automation.md`

## Sources

- https://developers.cloudflare.com/notifications/
- https://developers.cloudflare.com/notifications/get-started/configure-webhooks/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
