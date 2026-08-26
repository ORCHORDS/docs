# Cloudflare Notifications to Slack via Workers Webhook

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Cloudflare Notifications (Health Checks, DDoS alerts, Workers script errors, Logpush job failures) arrive as generic emails or PagerDuty incidents that the on-call team misses during working hours. You need a lightweight Workers webhook bridge that transforms Cloudflare alert payloads into formatted Slack messages routed by severity and alert type.

## Context

Cloudflare's notification system supports webhook destinations in addition to email and PagerDuty. A Worker acts as the webhook receiver, validates the request with an HMAC secret, maps the alert type to a Slack channel and message format, and forwards the payload to the Slack Incoming Webhooks API. This eliminates the PagerDuty intermediary for non-critical notifications and centralises alert routing logic in a single deployable Worker.

## 1. Create the Webhook Receiver Worker

```typescript
// src/index.ts
import { verifyCloudflareSignature } from "./verify";
import { buildSlackMessage } from "./formatter";
import { routeToChannel } from "./router";

export interface Env {
  CF_WEBHOOK_SECRET: string;        // secret set in Cloudflare Notifications UI
  SLACK_WEBHOOK_DEFAULT: string;    // Slack Incoming Webhook URL for general alerts
  SLACK_WEBHOOK_CRITICAL: string;   // separate channel for critical / P1 alerts
  SLACK_WEBHOOK_OPS: string;        // infra/ops channel
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const rawBody = await request.text();

    const valid = await verifyCloudflareSignature(
      rawBody,
      request.headers.get("cf-webhook-auth") ?? "",
      env.CF_WEBHOOK_SECRET
    );

    if (!valid) {
      return new Response("Unauthorized", { status: 401 });
    }

    let payload: CloudflareAlertPayload;
    try {
      payload = JSON.parse(rawBody) as CloudflareAlertPayload;
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    const slackUrl = routeToChannel(payload, env);
    const slackBody = buildSlackMessage(payload);

    const slackResp = await fetch(slackUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(slackBody),
    });

    if (!slackResp.ok) {
      console.error("Slack delivery failed", slackResp.status, await slackResp.text());
      return new Response("Upstream error", { status: 502 });
    }

    return new Response("OK", { status: 200 });
  },
} satisfies ExportedHandler<Env>;

export interface CloudflareAlertPayload {
  name: string;           // alert type, e.g. "workers_script_list"
  text: string;           // human-readable description
  data: Record<string, unknown>;
  ts: string;             // ISO 8601 timestamp
  alert_type: string;     // machine-readable type identifier
}
```

## 2. HMAC Signature Verification

```typescript
// src/verify.ts
export async function verifyCloudflareSignature(
  body: string,
  receivedSignature: string,
  secret: string
): Promise<boolean> {
  if (!receivedSignature || !secret) return false;

  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );

  // Cloudflare sends: "time=<unix_ts>,v1=<hex_hmac>"
  const parts = Object.fromEntries(
    receivedSignature.split(",").map((s) => s.split("=") as [string, string])
  );

  const signingPayload = `${parts.time}.${body}`;
  const expectedBytes = hexToBytes(parts.v1 ?? "");

  return crypto.subtle.verify(
    "HMAC",
    key,
    expectedBytes,
    encoder.encode(signingPayload)
  );
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}
```

## 3. Alert-Type to Channel Router

```typescript
// src/router.ts
import type { CloudflareAlertPayload, Env } from "./index";

const CRITICAL_TYPES = new Set([
  "dos_attack_l7",
  "dos_attack_l4",
  "workers_script_list",       // script upload errors that block deploys
  "load_balancing_health_alert",
  "advanced_http_alert_error",
]);

const OPS_TYPES = new Set([
  "logpush_health_alert",
  "failing_logpush_job_disabled",
  "expiring_zone_tls_certificate",
  "ssl_vip_deactivation",
  "zone_aop_custom_certificate_expiration_type",
]);

export function routeToChannel(
  payload: CloudflareAlertPayload,
  env: Env
): string {
  if (CRITICAL_TYPES.has(payload.alert_type)) {
    return env.SLACK_WEBHOOK_CRITICAL;
  }
  if (OPS_TYPES.has(payload.alert_type)) {
    return env.SLACK_WEBHOOK_OPS;
  }
  return env.SLACK_WEBHOOK_DEFAULT;
}
```

## 4. Slack Message Formatter

```typescript
// src/formatter.ts
import type { CloudflareAlertPayload } from "./index";

interface SlackMessage {
  text: string;
  blocks: SlackBlock[];
}

interface SlackBlock {
  type: string;
  text?: { type: string; text: string };
  fields?: Array<{ type: string; text: string }>;
}

const SEVERITY_EMOJI: Record<string, string> = {
  dos_attack_l7: ":rotating_light:",
  dos_attack_l4: ":rotating_light:",
  load_balancing_health_alert: ":warning:",
  logpush_health_alert: ":warning:",
  failing_logpush_job_disabled: ":x:",
  expiring_zone_tls_certificate: ":lock:",
  default: ":bell:",
};

export function buildSlackMessage(payload: CloudflareAlertPayload): SlackMessage {
  const emoji = SEVERITY_EMOJI[payload.alert_type] ?? SEVERITY_EMOJI.default;
  const ts = new Date(payload.ts).toISOString();

  return {
    text: `${emoji} Cloudflare Alert: ${payload.name}`,
    blocks: [
      {
        type: "header",
        text: {
          type: "plain_text",
          text: `${emoji} ${payload.name}`,
        },
      },
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: payload.text,
        },
      },
      {
        type: "section",
        fields: [
          { type: "mrkdwn", text: `*Type*\n\`${payload.alert_type}\`` },
          { type: "mrkdwn", text: `*Time*\n${ts}` },
        ],
      },
    ],
  };
}
```

## 5. wrangler.toml and Secrets

```toml
name = "cf-notifications-slack-bridge"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[vars]
# Non-sensitive vars only; use wrangler secret put for secrets
```

Set secrets via CLI:

```bash
wrangler secret put CF_WEBHOOK_SECRET
wrangler secret put SLACK_WEBHOOK_DEFAULT
wrangler secret put SLACK_WEBHOOK_CRITICAL
wrangler secret put SLACK_WEBHOOK_OPS
```

Configure the Cloudflare notification destination in the dashboard under **Notifications → Destinations → Add → Webhook**, using the Worker URL as the endpoint and the same value you set for `CF_WEBHOOK_SECRET`.

## 6. Delivery Audit Log via Analytics Engine

Track every alert delivery for audit and volume analysis.

```typescript
// Add to src/index.ts Env and handler
export interface Env {
  // ... existing fields
  ALERT_AUDIT: AnalyticsEngineDataset;
}

// Inside the fetch handler, after successful Slack delivery:
env.ALERT_AUDIT.writeDataPoint({
  blobs: [payload.alert_type, slackResp.status.toString()],
  doubles: [1],
  indexes: [payload.alert_type],
});
```

```toml
[[analytics_engine_datasets]]
binding = "ALERT_AUDIT"
dataset = "cf_notification_audit"
```

Query delivery counts by alert type:

```sql
SELECT
  blob1 AS alert_type,
  sum(double1) AS total_delivered,
  countIf(blob2 != '200') AS failed_deliveries
FROM cf_notification_audit
WHERE timestamp > now() - INTERVAL '7' DAY
GROUP BY alert_type
ORDER BY total_delivered DESC
```

## Anti-patterns

- **Skipping signature verification**: any party that discovers the Worker URL can spoof alert payloads and trigger Slack messages; always verify the HMAC before processing.
- **Using the same Slack channel for all alert types**: high-frequency informational alerts (certificate renewal, Logpush health) drown out critical DDoS and health-check alerts.
- **Returning 2xx even when Slack delivery fails**: Cloudflare retries failed webhook deliveries only if the receiver returns a non-2xx response; return 502 on upstream failure.
- **Hardcoding Slack webhook URLs as wrangler.toml `[vars]`**: these URLs grant posting rights to your Slack workspace; treat them as secrets, not configuration.
- **Not logging the `alert_type` field**: the raw `name` field can change with Cloudflare product updates; `alert_type` is the stable machine-readable identifier.

## Gotchas

- Cloudflare's signature format is `time=<unix_seconds>,v1=<hex_hmac_sha256>` where the HMAC input is `<time>.<raw_body>` — the period delimiter is mandatory and often misread as a dot in the timestamp.
- Slack Incoming Webhooks return HTTP 200 with body `"ok"` on success, but return 400 with a text error body (not JSON) for malformed payloads; check `slackResp.ok`, not the body text.
- Cloudflare notification webhooks have a 30-second delivery timeout; ensure the Worker completes within that window, including the outbound Slack fetch.
- The `cf-webhook-auth` header name is lowercase; `Headers.get()` is case-insensitive in the Workers runtime, but double-check if using raw header maps.

## Verification

1. Deploy the Worker with `wrangler deploy` and note the Worker URL.
2. Configure a test notification in Cloudflare dashboard (e.g. a manually triggered Health Check alert) with the Worker URL as webhook destination.
3. Trigger the notification; confirm the Slack message appears in the correct channel within 10 seconds.
4. Send a POST request with an invalid `cf-webhook-auth` header; confirm the Worker returns 401.
5. Query the `cf_notification_audit` Analytics Engine dataset and confirm one row exists per delivery.

## Related

- `cloudflare-notifications-pagerduty-webhook.md`
- `workers-slo-burn-rate-cloudflare-notifications.md`
- `workers-error-alerting-pagerduty-integration.md`
- `incident-runbook-workers-status-page-automation.md`
- `incident-severity-classification-automation.md`

## Sources

- https://developers.cloudflare.com/notifications/
- https://developers.cloudflare.com/notifications/notification-available/
- https://api.slack.com/messaging/webhooks
