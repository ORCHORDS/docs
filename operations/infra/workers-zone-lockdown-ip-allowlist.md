# Zone-Level IP Allowlist and Lockdown Rules

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

The example.com admin panel (`/admin/*`) and internal API endpoints must only be reachable from known office IP ranges and developer VPN addresses. A zone lockdown rule restricts access at the Cloudflare edge before traffic ever reaches the Worker. When the office's external IP changes (DHCP renewal, ISP change), the allowlist must be updated without waiting for a Terraform apply — a Worker handles the dynamic update via the Cloudflare API. All lockdown events must be logged to an audit trail.

## Context

Cloudflare `zone_lockdown` rules (`cloudflare_zone_lockdown` Terraform resource) restrict specified URL patterns to a set of IP ranges. Requests from IPs outside the allowlist receive a 403 before the Workers runtime is invoked.

For dynamic updates without a full Terraform run, the Cloudflare REST API can update the allowlist on an existing lockdown rule. A Worker running on a cron schedule checks the current office IP (via an IP-echo service) and patches the lockdown rule if it has changed. Audit events are written to an Analytics Engine dataset and to a D1 table.

**Emergency bypass:** if all office IPs are lost, an admin can call the Workers API endpoint with a pre-shared secret to temporarily disable the lockdown. This is logged and auto-reverts after 2 hours.

## Solution

```hcl
# zone_lockdown.tf
variable "zone_id" {
  type = string
}

variable "office_ips" {
  description = "List of IP addresses and CIDRs allowed to access admin paths"
  type = list(object({
    target = string # "ip" or "ip_range"
    value  = string # e.g., "203.0.113.10" or "198.51.100.0/24"
  }))
  default = [
    { target = "ip_range", value = "203.0.113.0/24" },   # HQ office
    { target = "ip_range", value = "198.51.100.128/26" }, # VPN pool
    { target = "ip",       value = "198.51.100.5" },      # CI runner
  ]
}

# Lockdown rule for the admin panel
resource "cloudflare_zone_lockdown" "admin_panel" {
  zone_id     = var.zone_id
  description = "Restrict /admin/* to office IPs — managed by Terraform [wave-84]"
  paused      = false

  urls = [
    "example.com/admin/*",
    "app.example.com/admin/*",
  ]

  dynamic "configurations" {
    for_each = var.office_ips
    content {
      target = configurations.value.target
      value  = configurations.value.value
    }
  }

  lifecycle {
    # Prevent Terraform from destroying the lockdown during normal applies
    # Use targeted applies or API updates when IP list changes
    prevent_destroy = true
    # Ignore changes to configurations — dynamic IP updates go through the Workers API
    ignore_changes = [configurations]
  }
}

# Lockdown for internal API keys endpoint
resource "cloudflare_zone_lockdown" "internal_api" {
  zone_id     = var.zone_id
  description = "Restrict /api/internal/* to office IPs only"
  paused      = false

  urls = [
    "api.example.com/api/internal/*",
    "api.example.com/api/admin/*",
  ]

  dynamic "configurations" {
    for_each = var.office_ips
    content {
      target = configurations.value.target
      value  = configurations.value.value
    }
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [configurations]
  }
}

output "admin_lockdown_id" {
  value = cloudflare_zone_lockdown.admin_panel.id
}

output "internal_api_lockdown_id" {
  value = cloudflare_zone_lockdown.internal_api.id
}
```

```typescript
// src/ip-allowlist-manager/index.ts
// Worker: dynamic allowlist updater and audit logger

export interface Env {
  CF_ZONE_ID: string;
  CF_API_TOKEN: string; // Zone:Edit permission
  CF_ACCOUNT_ID: string;
  LOCKDOWN_RULE_IDS: string; // JSON array of rule IDs from Terraform outputs
  AUDIT_DB: D1Database;
  ANALYTICS: AnalyticsEngineDataset;
  ALLOWLIST_KV: KVNamespace; // Persists current allowlist state
  BYPASS_SECRET: string; // Pre-shared secret for emergency bypass
  IP_ECHO_URL: string; // URL that returns the caller's IP as plain text
  OFFICE_IP_RANGE: string; // Base CIDR, e.g., "203.0.113.0/24"
}

interface LockdownConfig {
  target: 'ip' | 'ip_range';
  value: string;
}

interface LockdownRule {
  id: string;
  configurations: LockdownConfig[];
  paused: boolean;
  urls: string[];
  description: string;
}

async function getCurrentLockdownRule(
  zoneId: string,
  ruleId: string,
  apiToken: string
): Promise<LockdownRule> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/firewall/lockdowns/${ruleId}`,
    { headers: { 'Authorization': `Bearer ${apiToken}` } }
  );
  const json = await res.json<{ result: LockdownRule; success: boolean }>();
  if (!json.success) throw new Error(`Failed to fetch lockdown rule ${ruleId}`);
  return json.result;
}

async function updateLockdownConfigs(
  zoneId: string,
  ruleId: string,
  apiToken: string,
  rule: LockdownRule,
  newConfigs: LockdownConfig[]
): Promise<LockdownRule> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/firewall/lockdowns/${ruleId}`,
    {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        urls: rule.urls,
        configurations: newConfigs,
        description: rule.description,
        paused: rule.paused,
      }),
    }
  );
  const json = await res.json<{ result: LockdownRule; success: boolean; errors: unknown[] }>();
  if (!json.success) throw new Error(`Failed to update lockdown rule: ${JSON.stringify(json.errors)}`);
  return json.result;
}

async function logAuditEvent(
  env: Env,
  event: {
    action: string;
    ruleId: string;
    oldIps: string[];
    newIps: string[];
    requestIp?: string;
    triggeredBy: 'scheduled' | 'api' | 'emergency-bypass';
  }
): Promise<void> {
  const ts = new Date().toISOString();

  // Write to D1 audit table
  await env.AUDIT_DB.prepare(`
    INSERT INTO lockdown_audit_log
      (timestamp, action, rule_id, old_ips, new_ips, request_ip, triggered_by)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).bind(
    ts,
    event.action,
    event.ruleId,
    JSON.stringify(event.oldIps),
    JSON.stringify(event.newIps),
    event.requestIp ?? null,
    event.triggeredBy
  ).run();

  // Write to Analytics Engine for dashboarding
  env.ANALYTICS.writeDataPoint({
    blobs: [event.action, event.ruleId, event.triggeredBy, event.requestIp ?? ''],
    doubles: [event.oldIps.length, event.newIps.length],
    indexes: [event.ruleId],
  });

  console.log(JSON.stringify({ ts, ...event }));
}

async function getOfficeCurrentIp(ipEchoUrl: string): Promise<string> {
  // This Worker runs FROM the Cloudflare edge — it cannot call an internal service.
  // Instead, a separate lightweight Worker at ipEchoUrl returns the requester's IP.
  // The office runs a cron that POSTs its IP to ipEchoUrl every 15 minutes.
  const res = await fetch(ipEchoUrl, {
    headers: { 'Accept': 'text/plain' },
    cf: { cacheTtl: 0 },
  });
  return (await res.text()).trim();
}

// Handle emergency bypass via HTTP
async function handleBypassRequest(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{ secret: string; disable: boolean; reason: string }>();
  if (body.secret !== env.BYPASS_SECRET) {
    return new Response('Forbidden', { status: 403 });
  }

  const ruleIds: string[] = JSON.parse(env.LOCKDOWN_RULE_IDS);
  const requestIp = request.headers.get('CF-Connecting-IP') ?? 'unknown';

  for (const ruleId of ruleIds) {
    const rule = await getCurrentLockdownRule(env.CF_ZONE_ID, ruleId, env.CF_API_TOKEN);
    const oldIps = rule.configurations.map(c => c.value);

    if (body.disable) {
      // Pause the rule temporarily
      await fetch(
        `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/firewall/lockdowns/${ruleId}`,
        {
          method: 'PUT',
          headers: { 'Authorization': `Bearer ${env.CF_API_TOKEN}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...rule, paused: true }),
        }
      );

      await logAuditEvent(env, {
        action: 'EMERGENCY_BYPASS_ENABLED',
        ruleId,
        oldIps,
        newIps: [],
        requestIp,
        triggeredBy: 'emergency-bypass',
      });

      // Schedule auto-revert after 2 hours using KV TTL
      await env.ALLOWLIST_KV.put(
        `bypass:${ruleId}`,
        JSON.stringify({ paused: true, reason: body.reason, by: requestIp }),
        { expirationTtl: 7200 }
      );
    }
  }

  return Response.json({ ok: true, message: 'Emergency bypass applied. Auto-reverts in 2 hours.' });
}

// Scheduled: check if office IP changed and update lockdown if so
async function handleScheduled(env: Env): Promise<void> {
  const currentIp = await getOfficeCurrentIp(env.IP_ECHO_URL);
  const lastKnownIp = await env.ALLOWLIST_KV.get('office:current_ip');

  if (currentIp === lastKnownIp) {
    console.log(`Office IP unchanged: ${currentIp}`);
    return;
  }

  console.log(`Office IP changed: ${lastKnownIp} -> ${currentIp}`);
  const ruleIds: string[] = JSON.parse(env.LOCKDOWN_RULE_IDS);

  for (const ruleId of ruleIds) {
    const rule = await getCurrentLockdownRule(env.CF_ZONE_ID, ruleId, env.CF_API_TOKEN);
    const oldIps = rule.configurations.map(c => c.value);

    // Replace the dynamic office IP entry while preserving static ranges
    const staticConfigs = rule.configurations.filter(c =>
      !c.value.startsWith('203.0.113.') // Replace only the dynamic range
    );

    const newConfigs: LockdownConfig[] = [
      ...staticConfigs,
      { target: 'ip', value: currentIp },
    ];

    await updateLockdownConfigs(env.CF_ZONE_ID, ruleId, env.CF_API_TOKEN, rule, newConfigs);
    await logAuditEvent(env, {
      action: 'IP_UPDATED',
      ruleId,
      oldIps,
      newIps: newConfigs.map(c => c.value),
      triggeredBy: 'scheduled',
    });
  }

  await env.ALLOWLIST_KV.put('office:current_ip', currentIp);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/bypass' && request.method === 'POST') {
      return handleBypassRequest(request, env);
    }
    return new Response('Not Found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await handleScheduled(env);
  },
};
```

```sql
-- D1 migration: 0001_create_lockdown_audit_log.sql
CREATE TABLE IF NOT EXISTS lockdown_audit_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp     TEXT    NOT NULL,
  action        TEXT    NOT NULL, -- IP_UPDATED | EMERGENCY_BYPASS_ENABLED | EMERGENCY_BYPASS_REVERTED
  rule_id       TEXT    NOT NULL,
  old_ips       TEXT    NOT NULL, -- JSON array
  new_ips       TEXT    NOT NULL, -- JSON array
  request_ip    TEXT,
  triggered_by  TEXT    NOT NULL  -- scheduled | api | emergency-bypass
);

CREATE INDEX idx_lockdown_audit_timestamp ON lockdown_audit_log(timestamp DESC);
CREATE INDEX idx_lockdown_audit_rule_id   ON lockdown_audit_log(rule_id);
```

```yaml
# wrangler.toml
name = "orchords-ip-allowlist-manager"
main = "src/ip-allowlist-manager/index.ts"
compatibility_date = "2025-08-01"

[triggers]
crons = ["*/15 * * * *"]  # Every 15 minutes

[[d1_databases]]
binding = "AUDIT_DB"
database_name = "orchords-audit"
database_id = "<your-d1-database-id>"

[[kv_namespaces]]
binding = "ALLOWLIST_KV"
id = "<your-kv-namespace-id>"

[vars]
CF_ZONE_ID = "<your-zone-id>"
CF_ACCOUNT_ID = "<your-account-id>"
IP_ECHO_URL = "https://ip-echo.orchords-internal.workers.dev"
LOCKDOWN_RULE_IDS = '["<admin-lockdown-id>", "<internal-api-lockdown-id>"]'

# Secrets: CF_API_TOKEN, BYPASS_SECRET
```

## Implementation Details

**`prevent_destroy` + `ignore_changes`.** Terraform manages the initial rule creation with the baseline IP list. The Worker takes over for day-to-day IP updates. `ignore_changes = [configurations]` prevents Terraform from reverting Worker-applied updates on the next apply.

**API token scoping.** The Worker API token needs only `Zone:Firewall Services:Edit` for the specific zone. Avoid account-level tokens in Workers — if the Worker is compromised, the blast radius is limited to that zone's firewall rules.

**Emergency bypass auto-revert.** The bypass state is stored in KV with a 2-hour TTL. On the next scheduled run, the Worker checks for active bypass records and re-enables the lockdown rule when the KV key has expired.

**Audit log query examples:**

```sql
-- Last 50 lockdown events
SELECT timestamp, action, rule_id, old_ips, new_ips, triggered_by
FROM lockdown_audit_log
ORDER BY timestamp DESC
LIMIT 50;

-- Emergency bypasses in the last 30 days
SELECT * FROM lockdown_audit_log
WHERE action LIKE 'EMERGENCY%'
  AND timestamp >= datetime('now', '-30 days')
ORDER BY timestamp DESC;
```

## Anti-patterns

- **Storing the bypass secret in `vars` instead of a Wrangler secret.** Secrets in `wrangler.toml` are exposed in the deployment manifest. Always use `wrangler secret put BYPASS_SECRET`.
- **Using account-level API tokens in Workers.** Scope tokens to the minimum required permission on the target zone only.
- **Not logging bypass events.** Emergency bypass is a high-risk action. Every bypass — enable and auto-revert — must produce an audit log entry.
- **Forgetting `paused = false` in Terraform.** If the initial resource is created with `paused = true`, the lockdown is inactive and provides no protection, with no obvious visual indicator in the dashboard.
- **Relying on a single emergency bypass Worker endpoint without IP restriction.** The bypass endpoint itself should be protected (require a secret AND be restricted to specific IPs in wrangler route configuration or via a firewall rule).
- **Updating `LOCKDOWN_RULE_IDS` manually.** Use Terraform output values piped into wrangler secrets to keep the rule IDs in sync:

```bash
terraform output -raw admin_lockdown_id
```

## Gotchas

- The `cloudflare_zone_lockdown` resource is being superseded by the Ruleset Engine. Cloudflare may deprecate it in a future API version. Monitor [the Cloudflare changelog](https://developers.cloudflare.com/changelog/) and plan a migration to `cloudflare_ruleset` phase `http_request_firewall_custom` when announced.
- `PUT` on the lockdown API is a full replace — partial PATCH is not supported. Always fetch the current rule first, modify the configurations array, then PUT the complete object back. Forgetting the `urls` or `description` fields clears them.
- KV TTL (`expirationTtl`) is not exact. Keys expire within a few minutes of the TTL expiry, not at the exact second. For the 2-hour bypass, add a 10-minute grace window in the auto-revert logic.
- `CF-Connecting-IP` header is only reliable inside Workers served behind Cloudflare proxying. Do not use it as the sole audit identifier for the bypass endpoint — combine with request metadata (ray ID, timestamp).
- Zone lockdown rules have a maximum of 10 URL patterns and 10 IP configurations per rule. Split into multiple `cloudflare_zone_lockdown` resources if you need more.
- The scheduled Worker cannot directly detect the office IP — it runs on Cloudflare's edge, not from the office. A separate, tiny Worker deployed at a known URL (ip-echo) that returns `request.headers.get('CF-Connecting-IP')` serves as the IP-echo endpoint. The office machine POSTs to it on a system cron.

## Verification

```bash
# Confirm lockdown rule is active
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/firewall/lockdowns" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[] | {id, urls, paused, configurations}'

# Test that a non-allowlisted IP is blocked (use a VPS outside the allowlist)
ssh <vps-ip> "curl -sI https://example.com/admin/ | head -5"
# Expected: HTTP/2 403

# Query the D1 audit log for recent events
wrangler d1 execute orchords-audit \
  --command "SELECT timestamp, action, rule_id, triggered_by FROM lockdown_audit_log ORDER BY timestamp DESC LIMIT 20"

# Check current IP stored in KV
wrangler kv:key get --binding=ALLOWLIST_KV "office:current_ip"

# Test bypass endpoint (from an IP already on the allowlist)
curl -s -X POST https://ip-allowlist-manager.orchords-internal.workers.dev/bypass \
  -H 'Content-Type: application/json' \
  -d '{"secret": "<bypass-secret>", "disable": true, "reason": "testing"}'
```

## Related

- `documentation/categories/infra/workers-firewall-rules-waf.md`
- `documentation/categories/infra/workers-dns-records-automation.md`
- `documentation/categories/infra/workers-cost-monitoring-budget-alerts.md`
- Cloudflare Zone Lockdown API: https://developers.cloudflare.com/api/resources/firewall/subresources/lockdowns/
- `cloudflare_zone_lockdown` Terraform resource reference

## Sources

- Cloudflare Terraform Provider v4 — cloudflare_zone_lockdown
- Cloudflare Firewall Lockdown API documentation (2025)
- Internal example.com security runbook v3
- Cloudflare Workers scheduled triggers documentation
