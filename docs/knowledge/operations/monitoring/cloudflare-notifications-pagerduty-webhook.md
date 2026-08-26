# Real-Time Alerting: Cloudflare Notifications to PagerDuty via Webhook

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use Case

Your infrastructure relies on Cloudflare for DDoS mitigation, WAF, zone health, and Workers availability. When Cloudflare detects an attack, a health event, or a billing threshold breach, you want your on-call engineer paged immediately through PagerDuty—without building a polling loop or a separate monitoring Worker. You need to wire Cloudflare's built-in Notification system directly to PagerDuty's Events API v2 via webhook, validate the payload authenticity, and route alerts to the correct PagerDuty service and escalation policy.

---

## Context

Cloudflare's **Notification** system (available under Account → Notifications in the dashboard, or via the Cloudflare API) emits webhooks for dozens of platform events: DDoS attacks detected, WAF rule triggers, SSL certificate expiry, zone health changes, Workers script errors at the account level, Cloudflare Radar anomalies, D1 usage thresholds, and more.

Cloudflare signs webhook payloads with an HMAC-SHA256 signature using a shared secret. The signature appears in the `cf-webhook-auth` header. Verifying this before acting on the payload prevents attackers from spoofing alerts.

PagerDuty's **Events API v2** accepts `trigger`, `acknowledge`, and `resolve` event types. A Workers endpoint acts as the translation layer: it receives the Cloudflare webhook, verifies the signature, maps the Cloudflare alert type to a PagerDuty severity and service routing key, and forwards the event.

This pattern covers **Cloudflare platform notifications**, not application-level errors thrown by your own Workers code (see `workers-error-alerting-pagerduty-integration.md` for that).

---

## Configuring Cloudflare Notifications in the Dashboard

1. Go to **Account Home → Notifications → Add Notification**.
2. Select an alert type (e.g., **DDoS Attack L7** or **Health Check Status Change**).
3. Under **Connected Webhooks**, click **Add Webhook Destination**.
4. Set the URL to your Workers endpoint: `https://alerts.example.workers.dev/cloudflare-webhook`.
5. Cloudflare generates a **webhook secret**. Copy it—it is shown only once.
6. Save the notification. Cloudflare sends a test ping immediately; your endpoint must return HTTP 200.

---

## The Receiver Worker

```typescript
// workers/src/index.ts

interface Env {
  WEBHOOK_SECRET: string;         // Cloudflare webhook signing secret
  PD_ROUTING_KEY_DDOS: string;    // PagerDuty integration key for DDoS service
  PD_ROUTING_KEY_WAF: string;     // PagerDuty integration key for WAF service
  PD_ROUTING_KEY_DEFAULT: string; // Fallback PagerDuty service key
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const bodyText = await request.text();

    // --- Signature verification ---
    const cfSignature = request.headers.get("cf-webhook-auth");
    if (!cfSignature) {
      return new Response("Missing signature", { status: 401 });
    }

    const isValid = await verifySignature(bodyText, cfSignature, env.WEBHOOK_SECRET);
    if (!isValid) {
      return new Response("Invalid signature", { status: 401 });
    }

    let payload: CloudflareNotification;
    try {
      payload = JSON.parse(bodyText);
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    // Cloudflare sends a test ping with alert_type = "test"
    if (payload.data?.alert_type === "test") {
      console.log("Cloudflare webhook test ping received");
      return new Response("ok", { status: 200 });
    }

    const pdEvent = mapToPagerDuty(payload, env);
    const resp = await forwardToPagerDuty(pdEvent);

    if (!resp.ok) {
      const errorBody = await resp.text();
      console.error("PagerDuty rejected event", { status: resp.status, body: errorBody });
      return new Response("Upstream error", { status: 502 });
    }

    return new Response("ok", { status: 200 });
  },
};
```

---

## Signature Verification

```typescript
// workers/src/verify.ts

export async function verifySignature(
  body: string,
  signature: string,
  secret: string
): Promise<boolean> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const signatureBytes = encoder.encode(body);
  const computedBuffer = await crypto.subtle.sign("HMAC", key, signatureBytes);
  const computedHex = Array.from(new Uint8Array(computedBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  // Constant-time comparison to prevent timing attacks
  return timingSafeEqual(computedHex, signature);
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}
```

> **Important:** `crypto.subtle.timingSafeEqual` is not available in all Workers runtimes. The XOR loop above provides constant-time comparison without relying on that API.

---

## Mapping Cloudflare Alert Types to PagerDuty Events

```typescript
// workers/src/mapping.ts

export interface CloudflareNotification {
  id: string;
  timestamp: string;
  data: {
    alert_type: string;
    zone_id?: string;
    zone_name?: string;
    description?: string;
    impact?: string;

  };
}

export interface PagerDutyEvent {
  routing_key: string;
  event_action: "trigger" | "acknowledge" | "resolve";
  dedup_key?: string;
  payload: {
    summary: string;
    source: string;
    severity: "critical" | "error" | "warning" | "info";
    timestamp: string;
    group?: string;
    class?: string;
    custom_details: Record<string, unknown>;
  };
  links?: Array<{ href: string; text: string }>;
}

const ALERT_TYPE_MAP: Record<
  string,
  { severity: PagerDutyEvent["payload"]["severity"]; routingKeyEnvVar: string; group: string }
> = {
  // DDoS
  "dos_attack_l7": { severity: "critical", routingKeyEnvVar: "PD_ROUTING_KEY_DDOS", group: "ddos" },
  "dos_attack_l4": { severity: "critical", routingKeyEnvVar: "PD_ROUTING_KEY_DDOS", group: "ddos" },

  // WAF
  "waf_alert": { severity: "error", routingKeyEnvVar: "PD_ROUTING_KEY_WAF", group: "waf" },
  "waf_attack_detected": { severity: "error", routingKeyEnvVar: "PD_ROUTING_KEY_WAF", group: "waf" },

  // Health
  "health_check_status_notification": { severity: "critical", routingKeyEnvVar: "PD_ROUTING_KEY_DEFAULT", group: "health" },
  "origin_error_rate_alert": { severity: "error", routingKeyEnvVar: "PD_ROUTING_KEY_DEFAULT", group: "health" },

  // SSL/TLS
  "advanced_certificate_alert": { severity: "warning", routingKeyEnvVar: "PD_ROUTING_KEY_DEFAULT", group: "tls" },
  "expiring_zone_ssl_certificate": { severity: "warning", routingKeyEnvVar: "PD_ROUTING_KEY_DEFAULT", group: "tls" },

  // Workers
  "workers_alert": { severity: "error", routingKeyEnvVar: "PD_ROUTING_KEY_DEFAULT", group: "workers" },

  // D1 / KV usage
  "d1_database_query_limit_alert": { severity: "warning", routingKeyEnvVar: "PD_ROUTING_KEY_DEFAULT", group: "storage" },
};

export function mapToPagerDuty(
  notification: CloudflareNotification,
  env: Record<string, string>
): PagerDutyEvent {
  const alertType = notification.data.alert_type ?? "unknown";
  const mapping = ALERT_TYPE_MAP[alertType] ?? {
    severity: "warning" as const,
    routingKeyEnvVar: "PD_ROUTING_KEY_DEFAULT",
    group: "cloudflare",
  };

  const routingKey = env[mapping.routingKeyEnvVar] ?? env["PD_ROUTING_KEY_DEFAULT"];
  const zone = notification.data.zone_name ?? notification.data.zone_id ?? "account";

  return {
    routing_key: routingKey,
    event_action: "trigger",
    dedup_key: `cf-${notification.id}`, // Cloudflare notification IDs are unique; prevents duplicate pages
    payload: {
      summary: notification.data.description ?? `Cloudflare ${alertType} on ${zone}`,
      source: `cloudflare/${zone}`,
      severity: mapping.severity,
      timestamp: notification.timestamp,
      group: mapping.group,
      class: alertType,
      custom_details: notification.data,
    },
    links: [
      {
        href: `https://dash.cloudflare.com/?to=/:account/notifications`,
        text: "Cloudflare Notifications Dashboard",
      },
    ],
  };
}
```

```typescript
// workers/src/index.ts (continued)

async function forwardToPagerDuty(event: PagerDutyEvent): Promise<Response> {
  return fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
  });
}
```

---

## Registering the Webhook via the Cloudflare API

```bash
# Step 1: Create a webhook destination
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/alerting/v3/destinations/webhooks" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "PagerDuty Receiver (Workers)",
    "url": "https://alerts.example.workers.dev/cloudflare-webhook",
    "secret": "'"${WEBHOOK_SECRET}"'"
  }'
# Response includes { "result": { "id": "webhook-uuid" } }

# Step 2: Create a notification policy using the webhook
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/alerting/v3/policies" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "DDoS to PagerDuty",
    "alert_type": "dos_attack_l7",
    "enabled": true,
    "filters": {},
    "mechanisms": {
      "webhooks": [{ "id": "'"${WEBHOOK_UUID}"'" }]
    }
  }'
```

---

## wrangler.toml and Secret Configuration

```toml
name = "cf-alerts-receiver"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
# Non-sensitive config only; secrets go via `wrangler secret put`

routes = [
  { pattern = "alerts.example.com/cloudflare-webhook", zone_name = "example.com" }
]
```

```bash
wrangler secret put WEBHOOK_SECRET
wrangler secret put PD_ROUTING_KEY_DDOS
wrangler secret put PD_ROUTING_KEY_WAF
wrangler secret put PD_ROUTING_KEY_DEFAULT
```

---

## Anti-Patterns

**Accepting webhook payloads without verifying the HMAC signature.** Anyone who knows your Worker URL can forge Cloudflare alerts and page your on-call team at 3 AM with phantom incidents.

**Using the same PagerDuty routing key for all alert types.** DDoS alerts and certificate expiry warnings should route to different escalation policies and different on-call rotations.

**Not setting `dedup_key`.** Without a stable dedup key, Cloudflare retries (on HTTP 5xx responses) create multiple PagerDuty incidents for the same event. Use the Cloudflare notification `id` field as the dedup key.

**Responding synchronously to PagerDuty.** If PagerDuty is slow, your Worker holds the connection open and eventually returns 524 to Cloudflare, which retries. Use `ctx.waitUntil()` to forward the event asynchronously after responding 200 to Cloudflare immediately.

**Ignoring test pings.** Cloudflare sends a test ping when a webhook is first registered. If your endpoint does not respond 200 to the test ping, the webhook is never saved.

---

## Gotchas

- **Cloudflare notification `id` format** has changed over time. As of 2025, it is a UUID-like string. Do not assume a numeric format.
- **Rate limiting.** PagerDuty's Events API v2 rate limit is 120 requests per minute per routing key. During a mass DDoS event, Cloudflare may fire multiple notifications. Deduplicate aggressively with `dedup_key`.
- **Cloudflare retries.** Cloudflare retries webhook delivery up to 3 times with exponential backoff if your endpoint returns a non-2xx response or times out after 15 seconds. Make the endpoint idempotent.
- **Alert type list is account-plan-dependent.** DDoS L4 notifications require a paid plan. Review available alert types in the Cloudflare dashboard under **Notifications → Alert Types** for your plan.
- **Zone vs Account scope.** Some notifications are per-zone (WAF, health checks) and some are per-account (Workers script errors, billing). The webhook destination must be registered at the account level; zone-level notification policies reference it by webhook ID.
- **`cf-webhook-auth` header.** Cloudflare's documentation occasionally refers to this header as `x-cf-webhook-auth`. Check the actual header name in the test ping payload before hardcoding it.

---

## Verification

```bash
# Send a synthetic test ping from Cloudflare
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/alerting/v3/destinations/webhooks/${WEBHOOK_UUID}/test" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"

# Your Worker logs should show: "Cloudflare webhook test ping received"
# Worker should respond HTTP 200

# Simulate a full DDoS notification payload
BODY='{"id":"test-notif-001","timestamp":"2026-08-22T10:00:00Z","data":{"alert_type":"dos_attack_l7","zone_name":"example.com","description":"DDoS attack detected"}}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" -hex | cut -d' ' -f2)

curl -X POST https://alerts.example.workers.dev/cloudflare-webhook \
  -H "Content-Type: application/json" \
  -H "cf-webhook-auth: $SIG" \
  -d "$BODY"

# Verify in PagerDuty: a new incident triggered on the DDoS service
# Verify dedup: repeat the same curl; no new incident should be created (dedup_key match)
```

---

## Related

- `workers-error-alerting-pagerduty-integration.md` — application-level error alerting from Worker code
- `pagerduty-integration.md` — generic PagerDuty Events API setup
- `pagerduty-escalation-policies.md` — routing and escalation policy design
- `cloudflare-health-checks-origin-monitoring.md` — Cloudflare origin health check configuration
- `alert-severity-levels.md` — severity classification framework
- `escalation-policy-design.md` — on-call escalation trees

---

## Sources

- [Cloudflare Notifications documentation](https://developers.cloudflare.com/notifications/)
- [Cloudflare Webhooks documentation](https://developers.cloudflare.com/notifications/get-started/configure-webhooks/)
- [PagerDuty Events API v2](https://developer.pagerduty.com/docs/events-api-v2/trigger-events/)
- [Cloudflare Notification alert types list](https://developers.cloudflare.com/notifications/notification-available/)
