# Workers Email Routing Deploy Automation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project needs to receive inbound email at `@example.com` addresses, process it (parse, triage, route to the right tenant), and forward or respond — all via Cloudflare Email Routing and a Worker. The challenge is that Email Routing rules are API-managed objects that must be provisioned before the email Worker is deployed, and each environment (staging, production) needs separate routing rules pointing to separate Workers. Without automation, rules drift between environments and deploys overwrite rules silently.

## Context

Cloudflare Email Routing lets you define routing rules (match address → action: forward/drop/Worker) on a zone. An `email` handler in a Worker processes the `EmailMessage` passed to it. Because Email Routing rules are zone-level resources, not Worker-level resources, they are not declared in `wrangler.toml` and are not managed by `wrangler deploy`. You must provision them via the Cloudflare API (or Terraform) as a separate step. `wrangler.toml` only declares the `[[email]]` handler binding.

---

## 1. Email Worker Source

```typescript
// src/email-handler.ts
import { EmailMessage } from "cloudflare:email";
import PostalMime from "postal-mime";

export interface Env {
  DB: D1Database;
  FORWARD_ADDRESS: string; // e.g. "ops@internal.example.com"
}

export default {
  async email(message: EmailMessage, env: Env, _ctx: ExecutionContext): Promise<void> {
    const parser = new PostalMime();
    const parsed = await parser.parse(await new Response(message.raw).arrayBuffer());

    const tenantId = extractTenantFromAddress(message.to);

    if (!tenantId) {
      // Unknown destination — forward to ops inbox for manual triage
      await message.forward(env.FORWARD_ADDRESS);
      return;
    }

    // Store inbound email record in D1
    await env.DB.prepare(
      `INSERT INTO inbound_emails (tenant_id, from_address, subject, received_at)
       VALUES (?, ?, ?, ?)`
    )
      .bind(tenantId, message.from, parsed.subject ?? "(no subject)", new Date().toISOString())
      .run();

    // Auto-reply to acknowledge receipt
    const replyContent = new EmailMessage(
      message.to,                // from: the address it was sent to
      message.from,              // to: sender
      `Re: ${parsed.subject}`,
    );
    // For full reply bodies, use a raw MIME string via message.forward() to a reply Worker
    await message.forward(env.FORWARD_ADDRESS);
  },
};

function extractTenantFromAddress(address: string): string | null {
  // e.g. "tenant-abc@example.com" → "tenant-abc"
  const match = address.match(/^([a-z0-9-]+)@example project\.app$/i);
  return match ? match[1] : null;
}
```

---

## 2. wrangler.toml Email Binding

```toml
name = "example project-email-handler"
main = "src/email-handler.ts"
compatibility_date = "2025-09-01"

[env.staging]
[[env.staging.d1_databases]]
binding     = "DB"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # staging D1

[env.production]
[[env.production.d1_databases]]
binding     = "DB"
database_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"  # production D1
```

Note: `[[email]]` bindings are not declared in `wrangler.toml` for Email Routing Workers. The Worker simply exports an `email()` handler and is wired to Email Routing via an API rule.

---

## 3. Provisioning Email Routing Rules via API

Email Routing rules must be created before or immediately after the Worker deploy. Create a script that is idempotent — it checks for an existing rule before creating one:

```bash
#!/usr/bin/env bash
set -euo pipefail

ZONE_ID="${CF_ZONE_ID}"
API_TOKEN="${CF_API_TOKEN}"
WORKER_NAME="${1:-example project-email-handler}"  # the Worker to dispatch to
ENV="${2:-production}"

API="https://api.cloudflare.com/client/v4/zones/$ZONE_ID/email/routing/rules"

# Fetch existing rules
EXISTING=$(curl -s -H "Authorization: Bearer $API_TOKEN" "$API")
RULE_COUNT=$(echo "$EXISTING" | jq '[.result[] | select(.actions[].value == "'"$WORKER_NAME"'")] | length')

if [ "$RULE_COUNT" -gt "0" ]; then
  echo "Email routing rule for $WORKER_NAME already exists. Skipping."
  exit 0
fi

# Create catch-all rule → dispatch to Worker
curl -s -X POST "$API" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{ "type": "all" }],
    "actions":  [{ "type": "worker", "value": "'"$WORKER_NAME"'" }],
    "enabled":  true,
    "name":     "catch-all → '"$WORKER_NAME"' ('"$ENV"')"
  }' | jq '.success'
```

---

## 4. Per-Address Routing Rules for Multi-Tenant

For tenant-specific addresses, create explicit match rules per tenant rather than relying on catch-all routing in the Worker:

```typescript
// scripts/provision-tenant-routing.ts
const CF_API = "https://api.cloudflare.com/client/v4";

async function upsertTenantEmailRule(
  zoneId: string,
  apiToken: string,
  tenantId: string,
  workerName: string
): Promise<void> {
  const address = `${tenantId}@example.com`;

  // Check if rule already exists
  const existing = await fetch(`${CF_API}/zones/${zoneId}/email/routing/rules`, {
    headers: { Authorization: `Bearer ${apiToken}` },
  }).then((r) => r.json() as Promise<{ result: Array<{ matchers: Array<{ value?: string }>; actions: Array<{ value: string }> }> }>);

  const exists = existing.result?.some(
    (rule) =>
      rule.matchers.some((m) => m.value === address) &&
      rule.actions.some((a) => a.value === workerName)
  );

  if (exists) {
    console.log(`Rule for ${address} → ${workerName} already exists.`);
    return;
  }

  await fetch(`${CF_API}/zones/${zoneId}/email/routing/rules`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      matchers: [{ type: "literal", field: "to", value: address }],
      actions:  [{ type: "worker", value: workerName }],
      enabled:  true,
      name:     `Tenant ${tenantId} → ${workerName}`,
    }),
  });

  console.log(`Created routing rule: ${address} → ${workerName}`);
}
```

---

## 5. CI/CD Pipeline Order

```yaml
# .github/workflows/email-deploy.yml
name: Deploy Email Handler

on:
  push:
    branches: [main]
    paths:
      - "src/email-handler.ts"
      - "wrangler.toml"
      - "scripts/provision-email-routing.sh"

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy email Worker
        run: wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Provision email routing rules (idempotent)
        run: bash scripts/provision-email-routing.sh example project-email-handler production
        env:
          CF_ZONE_ID:  ${{ secrets.CF_ZONE_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Smoke test — send test email
        run: |
          # Use a mail client or API to send to smoke-test@example.com
          # Then query D1 for the inbound_emails row
          sleep 10
          COUNT=$(wrangler d1 execute example project-prod \
            --command "SELECT count(*) as c FROM inbound_emails WHERE from_address='ci@test.example.com'" \
            --env production --json | jq '.[0].results[0].c')
          echo "Inbound email records after smoke test: $COUNT"
```

---

## 6. Disabling Email Routing During Maintenance Windows

```bash
#!/usr/bin/env bash
# Disable all routing rules temporarily (e.g. during D1 migration)
ZONE_ID="${CF_ZONE_ID}"
API_TOKEN="${CF_API_TOKEN}"

curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/email/routing/rules" \
  -H "Authorization: Bearer $API_TOKEN" \
  | jq -r '.result[].id' \
  | while read -r RULE_ID; do
      curl -s -X PATCH \
        "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/email/routing/rules/$RULE_ID" \
        -H "Authorization: Bearer $API_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"enabled": false}' > /dev/null
      echo "Disabled rule $RULE_ID"
    done
```

---

## Anti-patterns

- Hardcoding the destination Worker name in routing rules as a static string that diverges from the actual deployed Worker name — after a rename, emails silently drop.
- Creating duplicate catch-all rules across environments that point to the same Worker — staging traffic routes to production Workers.
- Not enabling Email Routing on the zone before deploying the Worker — the Worker deploys successfully but never receives any messages.
- Deploying the email Worker after creating the routing rule — there is a race window where rules point to a Worker that does not yet exist and messages are dropped.

## Gotchas

- Email Routing Workers must be deployed to the **same account** as the zone — cross-account email dispatch is not supported.
- The `email()` handler must either `await message.forward()` or `await message.reply()` (or both) before the handler returns. Returning without forwarding silently drops the message.
- Cloudflare Email Routing does not support custom `From` address rewriting in Workers — the `from` field on forwarded messages is the original sender.
- Zone-level Email Routing must be enabled (via dashboard or API) before any routing rules or Worker dispatch works. Check `enabled: true` in `GET /zones/:zone/email/routing` before deploying rules.

## Verification

```bash
# Confirm Email Routing is enabled on the zone
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/email/routing" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.enabled'

# List active routing rules
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/email/routing/rules" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '[.result[] | {name,enabled,actions}]'

# Tail the email Worker for live log output
wrangler tail example project-email-handler --env production --format pretty
```

## Related

- `workers-d1-pre-deploy-migration-safety.md`
- `workers-queues-consumer-worker-deployment.md`
- `secrets-management-wrangler-vault.md`
- `deployment-verification-smoke-tests.md`
- `multi-region-dns-failover-routing.md`

## Sources

- https://developers.cloudflare.com/email-routing/
- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/api/operations/email-routing-routing-rules-list-routing-rules
- https://developers.cloudflare.com/email-routing/setup/
