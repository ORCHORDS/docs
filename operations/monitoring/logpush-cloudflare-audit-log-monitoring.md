# Logpush Cloudflare Audit Log Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Security-sensitive changes to your Cloudflare account — firewall rule edits, DNS mutations,
Worker script deployments, access policy changes — happen without real-time alerting. You need
a pipeline that streams Cloudflare audit logs to a destination you control and fires alerts for
high-risk actions within seconds.

## Context
Cloudflare Audit Logs capture every API-driven change to an account or zone and are accessible
via the Logpush `audit_logs` dataset. Unlike zone-scoped Logpush jobs, audit log jobs attach at
the **account** level and require the `Logs:Edit` permission. The recommended pipeline routes
Logpush to an R2 bucket (cold storage) and simultaneously feeds a lightweight Worker webhook
receiver that classifies events by severity and dispatches to PagerDuty or Slack.

---

## Section 1 — Logpush Job: Account-Level Audit Log Export to R2

Create the Logpush job via the Cloudflare API. You must use an account-level job, not a zone job.

```bash
# Create the audit log Logpush job (R2 destination)
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "name": "audit-log-r2",
    "dataset": "audit_logs",
    "destination_conf": "r2://<BUCKET_NAME>/audit-logs?account-id=<ACCOUNT_ID>&access-key-id=<R2_KEY>&secret-access-key=<R2_SECRET>",
    "output_options": {
      "field_names": [
        "ActionResult", "ActionType", "ActorEmail",
        "ActorID", "ActorIP", "ActorType",
        "ID", "Interface", "Metadata",
        "NewValue", "OldValue", "OwnerID",
        "ResourceID", "ResourceType", "When"
      ],
      "timestamp_format": "rfc3339",
      "output_type": "ndjson"
    },
    "enabled": true
  }'
```

R2 stores full NDJSON files partitioned by timestamp prefix (`audit-logs/YYYY-MM-DD/HH/`).
Add a lifecycle rule on the bucket to expire objects older than 365 days for compliance.

For real-time alerting, also configure a Logpush job to an HTTPS destination pointing to your
Worker webhook receiver (see Section 2).

---

## Section 2 — Worker Webhook Receiver: Real-Time Classification and Alerting

```typescript
// audit-log-receiver.ts
export interface Env {
  SLACK_WEBHOOK_URL: string;
  PAGERDUTY_ROUTING_KEY: string;
  LOGPUSH_SECRET: string; // shared secret passed as ?secret= query param
}

// Actions that warrant immediate PagerDuty alert
const CRITICAL_ACTIONS = new Set([
  "delete",
  "purge",
  "revoke",
  "disable",
]);

// Resource types that are always high-interest
const SENSITIVE_RESOURCES = new Set([
  "Worker Script",
  "Firewall Rule",
  "Access Application",
  "Access Policy",
  "API Token",
  "DNS Record",
  "Zone",
  "Account",
]);

interface AuditLogEntry {
  ActionResult: boolean;
  ActionType: string;
  ActorEmail: string;
  ActorID: string;
  ActorIP: string;
  ActorType: string;
  ID: string;
  Interface: string;
  Metadata: Record<string, unknown>;
  NewValue: string;
  OldValue: string;
  ResourceID: string;
  ResourceType: string;
  When: string;
}

function classifySeverity(entry: AuditLogEntry): "critical" | "high" | "low" {
  const action = (entry.ActionType ?? "").toLowerCase();
  const resource = entry.ResourceType ?? "";

  if (CRITICAL_ACTIONS.has(action) && SENSITIVE_RESOURCES.has(resource)) {
    return "critical";
  }
  if (SENSITIVE_RESOURCES.has(resource)) {
    return "high";
  }
  return "low";
}

async function alertPagerDuty(entry: AuditLogEntry, env: Env): Promise<void> {
  await fetch("https://events.pagerduty.com/v2/enqueue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      routing_key: env.PAGERDUTY_ROUTING_KEY,
      event_action: "trigger",
      dedup_key: entry.ID,
      payload: {
        summary: `[CF Audit] ${entry.ActionType} on ${entry.ResourceType} by ${entry.ActorEmail}`,
        severity: "critical",
        source: "cloudflare-audit-logs",
        timestamp: entry.When,
        custom_details: {
          actor_ip: entry.ActorIP,
          actor_type: entry.ActorType,
          resource_id: entry.ResourceID,
          result: entry.ActionResult,
          interface: entry.Interface,
        },
      },
    }),
  });
}

async function alertSlack(
  entry: AuditLogEntry,
  severity: "high" | "low",
  env: Env
): Promise<void> {
  const emoji = severity === "high" ? ":warning:" : ":information_source:";
  await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text:
        `${emoji} *Cloudflare Audit* | \`${entry.ActionType}\` on \`${entry.ResourceType}\`` +
        `\n• Actor: ${entry.ActorEmail} (${entry.ActorIP})` +
        `\n• Resource: ${entry.ResourceID}` +
        `\n• Result: ${entry.ActionResult ? "success" : "failure"}` +
        `\n• Time: ${entry.When}`,
    }),
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Validate shared secret
    const url = new URL(request.url);
    if (url.searchParams.get("secret") !== env.LOGPUSH_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.text();
    const lines = body.trim().split("\n");

    const alertPromises: Promise<void>[] = [];

    for (const line of lines) {
      if (!line.trim()) continue;
      let entry: AuditLogEntry;
      try {
        entry = JSON.parse(line) as AuditLogEntry;
      } catch {
        continue;
      }

      const severity = classifySeverity(entry);

      if (severity === "critical") {
        alertPromises.push(alertPagerDuty(entry, env));
        alertPromises.push(alertSlack(entry, "high", env));
      } else if (severity === "high") {
        alertPromises.push(alertSlack(entry, "high", env));
      }
      // "low" severity: stored in R2 only, no real-time alert
    }

    await Promise.allSettled(alertPromises);

    return new Response("OK", { status: 200 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Logpush HTTPS Destination and Wrangler Config

```bash
# Create a second Logpush job pointing at the Worker for real-time alerting
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{
    \"name\": \"audit-log-worker-realtime\",
    \"dataset\": \"audit_logs\",
    \"destination_conf\": \"https://audit-log-receiver.example.workers.dev?secret=<redacted-secret>
    \"output_options\": {
      \"field_names\": [
        \"ActionResult\", \"ActionType\", \"ActorEmail\",
        \"ActorID\", \"ActorIP\", \"ActorType\",
        \"ID\", \"Interface\", \"Metadata\",
        \"NewValue\", \"OldValue\", \"ResourceID\",
        \"ResourceType\", \"When\"
      ],
      \"timestamp_format\": \"rfc3339\",
      \"output_type\": \"ndjson\"
    },
    \"enabled\": true
  }"
```

```toml
# wrangler.toml for the receiver Worker
name = "audit-log-receiver"
main = "audit-log-receiver.ts"
compatibility_date = "2025-01-01"

[vars]
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."

[[secrets]]
# Set via: wrangler secret put PAGERDUTY_ROUTING_KEY
# Set via: wrangler secret put LOGPUSH_SECRET
```

---

## Anti-patterns
- Using a zone-level Logpush job for audit logs — audit logs are account-scoped and
  require an account-level job; zone jobs silently return an error or no data.
- Storing the Logpush shared secret in `[vars]` — it is visible in the Cloudflare dashboard;
  always use `wrangler secret put` to store it as an encrypted secret.
- Alerting on every audit log event — `OldValue`/`NewValue` writes from read-heavy automations
  flood Slack; filter to `SENSITIVE_RESOURCES` and fail-only (`ActionResult: false`) patterns first.
- Processing the entire payload synchronously before responding 200 — Logpush retries on
  non-2xx responses; use `ctx.waitUntil()` for downstream alerting so Logpush gets an
  immediate 200 acknowledgement.

## Gotchas
- Logpush to an HTTPS destination delivers in batches of up to 1,000 lines; your receiver
  must handle multi-line NDJSON bodies, not single JSON objects.
- The `audit_logs` dataset is account-scoped; the Logpush job URL path is
  `/accounts/{id}/logpush/jobs`, not `/zones/{id}/logpush/jobs`.
- `CF_API_TOKEN` must have `Logs:Edit` **and** `Account Settings:Read` permissions; the
  Logs:Edit permission alone is insufficient to list existing audit log jobs.
- Cloudflare delivers audit log entries with a delay of up to ~30 seconds; do not use the
  Logpush stream as your only layer — monitor the Cloudflare status page separately.

## Verification
```bash
# List all account-level Logpush jobs and confirm the audit_logs dataset job is enabled
curl "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | select(.dataset == "audit_logs")'

# Tail the receiver Worker to see incoming Logpush payloads live
wrangler tail audit-log-receiver --format pretty

# Manually query audit logs via the REST API to compare against Logpush output
curl "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/audit_logs?since=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)&per_page=25" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {action: .action.type, resource: .resource.type, actor: .actor.email}'
```

## Related
- `cloudflare-logpush-setup.md`
- `cloudflare-notifications-pagerduty-webhook.md`
- `cloudflare-notifications-slack-webhook-workers.md`
- `logpush-s3-compatible-r2-destination.md`
- `logpush-http-destination-custom-auth-headers.md`
- `zero-trust-access-login-audit-analytics-engine.md`
- `firewall-event-spike-anomaly-detection.md`

## Sources
- https://developers.cloudflare.com/logs/reference/log-fields/account/audit_logs/
- https://developers.cloudflare.com/logs/get-started/enable-destinations/http/
- https://developers.cloudflare.com/logs/get-started/enable-destinations/r2/
- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://developers.cloudflare.com/logs/logpush/examples/logpush-curl/
