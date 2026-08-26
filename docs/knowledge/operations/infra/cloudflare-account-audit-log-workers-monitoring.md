# Cloudflare Account Audit Log Workers Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Security or compliance teams need a real-time feed of Cloudflare account-level audit
events — API token creation, zone setting changes, Worker deployments, Access policy
modifications — pushed to a SIEM or alerting system. Manually polling the dashboard is
not auditable and misses events during off-hours. You need a scheduled Cloudflare
Worker that fetches audit logs via API, filters security-relevant events, and forwards
them to a downstream sink (Slack webhook, PagerDuty, Splunk HEC, or a D1 database).

---

## Context

Cloudflare exposes account audit logs at:

```
GET /client/v4/accounts/{account_id}/audit_logs
```

Events include `action.type` (e.g. `add`, `delete`, `update`), `resource.type` (e.g.
`zone`, `access_application`, `worker_script`, `api_token`), actor email, source IP,
and a `when` timestamp. The API is paginated and returns up to 1000 records per page.

A Cron-triggered Worker is the right tool because:
- It runs inside Cloudflare's network with low latency to the audit log API
- It can use D1 to track the last processed cursor, preventing duplicate alerts
- No external infrastructure to maintain

---

## 1. Wrangler Configuration

```toml
# wrangler.toml
name        = "audit-log-monitor"
main        = "src/index.ts"
compatibility_date  = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding  = "DB"
database_name = "audit-log-cursor"
database_id   = "<your-d1-database-id>"

[vars]
ACCOUNT_ID    = "<your-cloudflare-account-id>"
SLACK_CHANNEL = "#security-alerts"

[[triggers]]
crons = ["*/5 * * * *"]   # Every 5 minutes
```

Secrets (`CF_API_TOKEN`, `SLACK_WEBHOOK_URL`) are injected via `wrangler secret put`
or Terraform `cloudflare_worker_secret`.

---

## 2. Environment Type Definitions

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
  CF_API_TOKEN: string;
  ACCOUNT_ID: string;
  SLACK_WEBHOOK_URL: string;
  SLACK_CHANNEL: string;
}

export interface AuditLogEntry {
  id: string;
  action: { type: string; result: string };
  actor: { email: string; ip: string; type: string };
  resource: { type: string; id: string };
  interface: string;
  metadata: Record<string, unknown>;
  newValue: string;
  oldValue: string;
  owner: { id: string };
  when: string;  // ISO 8601
}

export interface AuditLogResponse {
  result: AuditLogEntry[];
  result_info: {
    count: number;
    page: number;
    per_page: number;
    total_count: number;
    cursors?: { before: string; after: string };
  };
  success: boolean;
  errors: { code: number; message: string }[];
}
```

---

## 3. D1 Schema for Cursor Tracking

```sql
-- migrations/0001_create_cursor.sql
CREATE TABLE IF NOT EXISTS audit_cursor (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Apply with:

```bash
wrangler d1 execute audit-log-cursor --file=migrations/0001_create_cursor.sql
```

Storing only a single cursor row per account means the table stays tiny and queries
are O(1).

---

## 4. Audit Log Fetcher

```typescript
// src/fetcher.ts
import type { AuditLogResponse, AuditLogEntry, Env } from "./types.js";

const BASE = "https://api.cloudflare.com/client/v4";

export async function fetchAuditLogs(
  env: Env,
  since: string,
  cursor?: string,
): Promise<{ entries: AuditLogEntry[]; nextCursor?: string }> {
  const url = new URL(`${BASE}/accounts/${env.ACCOUNT_ID}/audit_logs`);
  url.searchParams.set("since", since);
  url.searchParams.set("per_page", "100");
  if (cursor) url.searchParams.set("cursor", cursor);

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
  });

  if (!res.ok) {
    throw new Error(`Audit log API error: ${res.status} ${await res.text()}`);
  }

  const body: AuditLogResponse = await res.json();
  if (!body.success) {
    throw new Error(`Audit log API failure: ${JSON.stringify(body.errors)}`);
  }

  return {
    entries: body.result,
    nextCursor: body.result_info.cursors?.after,
  };
}
```

---

## 5. Alert Filter and Slack Notifier

```typescript
// src/alerter.ts
import type { AuditLogEntry, Env } from "./types.js";

// Resource types that always warrant an alert
const HIGH_SEVERITY_RESOURCES = new Set([
  "api_token",
  "access_application",
  "access_policy",
  "worker_secret",
  "zone_setting",
]);

// Action types that always warrant an alert
const HIGH_SEVERITY_ACTIONS = new Set([
  "delete",
  "create",
]);

export function isSevere(entry: AuditLogEntry): boolean {
  return (
    HIGH_SEVERITY_RESOURCES.has(entry.resource.type) &&
    HIGH_SEVERITY_ACTIONS.has(entry.action.type)
  );
}

export async function sendSlackAlert(
  entries: AuditLogEntry[],
  env: Env,
): Promise<void> {
  if (entries.length === 0) return;

  const blocks = entries.slice(0, 10).map((e) => ({
    type: "section",
    text: {
      type: "mrkdwn",
      text: [
        `*Action:* \`${e.action.type}\` on \`${e.resource.type}\``,
        `*Actor:* ${e.actor.email} (${e.actor.ip})`,
        `*Resource ID:* ${e.resource.id}`,
        `*Time:* ${e.when}`,
      ].join("\n"),
    },
  }));

  const payload = {
    channel: env.SLACK_CHANNEL,
    text: `⚠️ ${entries.length} high-severity Cloudflare audit event(s) detected`,
    blocks: [
      { type: "header", text: { type: "plain_text", text: "Cloudflare Audit Alert" } },
      ...blocks,
    ],
  };

  const res = await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    console.error(`Slack webhook failed: ${res.status}`);
  }
}
```

---

## 6. Main Worker Handler

```typescript
// src/index.ts
import { fetchAuditLogs } from "./fetcher.js";
import { isSevere, sendSlackAlert } from "./alerter.js";
import type { Env } from "./types.js";

const CURSOR_KEY = "last_processed_cursor";
const LOOKBACK_MINUTES = 10; // Safety window on first run

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runMonitor(env));
  },

  // Allow manual trigger via HTTP for testing
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });
    ctx.waitUntil(runMonitor(env));
    return new Response("Monitor triggered", { status: 202 });
  },
} satisfies ExportedHandler<Env>;

async function runMonitor(env: Env): Promise<void> {
  // Retrieve the last cursor from D1
  const row = await env.DB
    .prepare("SELECT value FROM audit_cursor WHERE key = ?")
    .bind(CURSOR_KEY)
    .first<{ value: string }>();

  // On first run, look back a safety window
  const since = row
    ? new Date(row.value).toISOString()
    : new Date(Date.now() - LOOKBACK_MINUTES * 60_000).toISOString();

  let cursor: string | undefined;
  const severe: Awaited<ReturnType<typeof fetchAuditLogs>>["entries"] = [];

  // Page through all results since last cursor
  do {
    const { entries, nextCursor } = await fetchAuditLogs(env, since, cursor);
    severe.push(...entries.filter(isSevere));
    cursor = nextCursor;
  } while (cursor);

  await sendSlackAlert(severe, env);

  // Persist cursor as current time
  const now = new Date().toISOString();
  await env.DB
    .prepare(
      "INSERT INTO audit_cursor (key, value, updated_at) VALUES (?, ?, ?) " +
      "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at"
    )
    .bind(CURSOR_KEY, now, now)
    .run();

  console.log(`Processed audit logs since ${since}; ${severe.length} severe events`);
}
```

---

## Anti-patterns

- **Polling without cursor persistence** — Re-processing the full log window on every
  run causes duplicate alerts and missed events if the lookback window is shorter than
  the polling interval during an incident.
- **Alerting on every audit event** — The Cloudflare audit log is high-volume. Filter
  to high-severity resource and action combinations; log everything else to D1 or
  Logpush for forensics.
- **Using a Global API Key** — The audit log endpoint works with scoped API tokens.
  Grant only `Account → Audit Logs → Read`.
- **Not handling pagination** — Events during busy periods can exceed 100 per poll
  window. Always follow `cursors.after` until it is absent.

---

## Gotchas

- The audit log API `since` parameter is inclusive. Using `now` as the cursor would
  re-process the boundary event. Store the cursor as the current time after processing
  completes, not the timestamp of the last event.
- `result_info.cursors` is absent when there are no more pages — always guard with
  optional chaining.
- Cloudflare audit logs have an API rate limit of 1200 requests per 5 minutes. A
  single monitor Worker run is well within limits, but multiple Workers in the same
  account sharing the same token can exhaust it.
- Cron triggers have a minimum interval of 1 minute. Sub-minute alerting requires
  an external push (Logpush to a SIEM) rather than a polling Worker.
- `ctx.waitUntil()` is required for scheduled handlers — without it, async work after
  the handler returns is cancelled.

---

## Verification

```bash
# Manual HTTP trigger (requires Worker route or wrangler dev)
curl -X POST https://audit-log-monitor.example.com/

# Check D1 cursor state
wrangler d1 execute audit-log-cursor \
  --command "SELECT key, value, updated_at FROM audit_cursor"

# Tail Worker logs in real time
wrangler tail audit-log-monitor --format pretty

# Confirm audit log API connectivity
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/audit_logs?per_page=5" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result | length'
```

---

## Related

- `cloudflare-logpush-terraform-pipeline.md`
- `cloudflare-network-analytics-ddos-forensics.md`
- `cloudflare-workers-api-token-scoping.md`
- `cloudflare-durable-objects-stateful-edge.md`
- `workers-opentelemetry-tail-workers.md`

---

## Sources

- Cloudflare Audit Logs API: https://developers.cloudflare.com/api/operations/audit-logs-get-account-audit-logs
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1 – Workers Binding: https://developers.cloudflare.com/d1/worker-api/
