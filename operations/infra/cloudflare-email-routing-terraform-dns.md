# Cloudflare Email Routing Terraform DNS Automation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You manage email routing rules for multiple domains — catch-all forwarders, per-alias routing to
team inboxes, and worker-processed addresses — and need to provision or migrate them reproducibly
across environments. Manual dashboard configuration makes auditing impossible and breaks CI/CD
when DNS records fall out of sync with routing rules. You need Terraform to own all email routing
resources: enabling the feature, managing MX/SPF/DMARC DNS records, and declaring address rules.

## Context

Cloudflare Email Routing lets you receive email at `@yourdomain.com` addresses and forward or
process them without an email server. The Cloudflare provider exposes four resources:

- `cloudflare_email_routing_settings` — enables/configures Email Routing per zone.
- `cloudflare_email_routing_address` — verifies a destination email address at the account level.
- `cloudflare_email_routing_rule` — maps a matcher (e.g. specific address) to an action (forward,
  drop, or deliver to a Worker).
- `cloudflare_email_routing_catch_all` — a zone-level default rule for unmatched addresses.

Enabling Email Routing automatically provisions required MX and SPF records; Terraform tracks them
via data sources or outputs.

---

## 1. Enable Email Routing on the Zone

```hcl
# email-routing.tf
variable "cloudflare_account_id" { type = string }
variable "zone_id"               { type = string }
variable "zone_name"             { type = string }  # e.g. "example.com"

resource "cloudflare_email_routing_settings" "main" {
  zone_id = var.zone_id
  enabled = true
}
```

When `enabled = true`, Cloudflare automatically adds MX records pointing to `route1.mx.cloudflare.net`,
`route2.mx.cloudflare.net`, and `route3.mx.cloudflare.net`. Do not manually add MX records for
the zone while Email Routing is enabled — they will conflict.

---

## 2. Verify Destination Addresses

```hcl
# destinations.tf
locals {
  destination_emails = [
    "support@company.io",
    "billing@company.io",
    "dev-alerts@company.io",
    "founders@company.io",
  ]
}

resource "cloudflare_email_routing_address" "dest" {
  for_each   = toset(local.destination_emails)
  account_id = var.cloudflare_account_id
  email      = each.value
}
```

Each destination address must complete an email verification flow. Terraform `apply` triggers the
verification email; the resource moves to `verified` state once the link is clicked. Verified
addresses are account-scoped and can be reused across multiple zones.

---

## 3. Per-Alias Forwarding Rules

```hcl
# rules.tf
locals {
  routing_rules = [
    { matcher_value = "support@${var.zone_name}",    destination = "support@company.io",    priority = 10 },
    { matcher_value = "billing@${var.zone_name}",    destination = "billing@company.io",    priority = 20 },
    { matcher_value = "jobs@${var.zone_name}",       destination = "founders@company.io",   priority = 30 },
    { matcher_value = "alerts@${var.zone_name}",     destination = "dev-alerts@company.io", priority = 40 },
  ]
}

resource "cloudflare_email_routing_rule" "forward" {
  count   = length(local.routing_rules)
  zone_id = var.zone_id
  name    = "forward-${split("@", local.routing_rules[count.index].matcher_value)[0]}"
  enabled = true

  matcher {
    type  = "literal"
    field = "to"
    value = local.routing_rules[count.index].matcher_value
  }

  action {
    type  = "forward"
    value = [local.routing_rules[count.index].destination]
  }

  priority = local.routing_rules[count.index].priority

  depends_on = [cloudflare_email_routing_settings.main]
}
```

---

## 4. Catch-All Rule

```hcl
# catch-all.tf
resource "cloudflare_email_routing_catch_all" "default" {
  zone_id = var.zone_id
  name    = "catch-all-drop"
  enabled = true

  matcher {
    type = "all"
  }

  # Drop unmatched emails (or change type to "forward" with a value list)
  action {
    type = "drop"
  }

  depends_on = [cloudflare_email_routing_settings.main]
}
```

To forward unmatched instead of drop:

```hcl
action {
  type  = "forward"
  value = ["catchall@company.io"]
}
```

---

## 5. Worker Email Processing

For addresses that need programmatic processing (spam scoring, ticket creation, auto-reply),
route to a Worker instead of a destination address:

```hcl
# worker-rule.tf
resource "cloudflare_email_routing_rule" "ticket_worker" {
  zone_id  = var.zone_id
  name     = "inbound-ticket-worker"
  enabled  = true
  priority = 5

  matcher {
    type  = "literal"
    field = "to"
    value = "tickets@${var.zone_name}"
  }

  action {
    type  = "worker"
    value = ["inbound-email-processor"]  # Worker name
  }

  depends_on = [cloudflare_email_routing_settings.main]
}
```

```typescript
// src/email-processor.ts
export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const subject = message.headers.get("subject") ?? "(no subject)";
    const from    = message.from;

    // Read the raw email body
    const body = await new Response(message.raw).text();

    // Create a support ticket
    await createTicket({ from, subject, body }, env);

    // Forward a copy to the archive inbox
    await message.forward("archive@company.io");
  },
};

interface Env {
  TICKET_API_KEY: string;
}

async function createTicket(
  data: { from: string; subject: string; body: string },
  env: Env
): Promise<void> {
  await fetch("https://tickets.company.io/api/ingest", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.TICKET_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });
}
```

---

## 6. SPF and DMARC Hardening

Cloudflare adds its own SPF include automatically, but you must manage your DMARC record and
merge any pre-existing SPF entries:

```hcl
# dns.tf
resource "cloudflare_record" "spf" {
  zone_id = var.zone_id
  name    = "@"
  type    = "TXT"
  value   = "v=spf1 include:_spf.mx.cloudflare.net include:sendgrid.net ~all"
  ttl     = 300

  depends_on = [cloudflare_email_routing_settings.main]
}

resource "cloudflare_record" "dmarc" {
  zone_id = var.zone_id
  name    = "_dmarc"
  type    = "TXT"
  value   = "v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@company.io; pct=100"
  ttl     = 300
}
```

---

## Anti-patterns

- **Adding MX records manually after enabling Email Routing.** Cloudflare manages MX records
  automatically; manual additions conflict and may cause delivery failures.
- **Using `type = "all"` matcher in a non-catch-all rule.** Only the `cloudflare_email_routing_catch_all`
  resource supports the `all` matcher type; using it in a `cloudflare_email_routing_rule` returns
  a validation error.
- **Forwarding to unverified destination addresses.** Rules referencing unverified destinations
  silently fail at delivery time. Always ensure `cloudflare_email_routing_address` resources reach
  `verified` state before creating rules that reference them.
- **Storing destination email lists in Terraform variables as plaintext in version control.**
  For sensitive forward targets (executive inboxes, security aliases), use Terraform `sensitive`
  variables or read from Vault/AWS Secrets Manager.

---

## Gotchas

- Email Routing cannot coexist with a custom mail server on the same zone. Enabling it removes
  pre-existing MX records pointing to external providers (G Suite, Fastmail, etc.).
- `cloudflare_email_routing_address` verification is out-of-band: Terraform creates the resource
  but cannot complete the verification automatically. CI plans will show the resource as present but
  the destination as `unverified` until a human clicks the link.
- Rule priority is an integer; lower numbers are matched first. Two rules at the same priority
  yield non-deterministic behavior — enforce unique priorities via your `locals` block.
- Workers bound via `type = "worker"` in an email rule must export an `email` handler, not only
  a `fetch` handler. A Worker without an `email` export will drop the message silently.

---

## Verification

```bash
# Confirm Email Routing is enabled
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/email/routing" \
  | jq '{enabled: .result.enabled, status: .result.status}'

# List active rules
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/email/routing/rules" \
  | jq '.result[] | {name, priority, enabled, matchers: .matchers[].value, actions: .actions[].type}'

# List verified destinations
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/email/routing/addresses" \
  | jq '.result[] | {email, verified}'

# Terraform clean state
terraform plan -detailed-exitcode
```

---

## Related

- `cloudflare-dns-api.md`
- `dns-management-2026.md`
- `reverse-dns-ptr-deliverability.md`
- `smtp-relay-outbound-architecture.md`
- `cloudflare-workers-api-token-scoping.md`

---

## Sources

- https://developers.cloudflare.com/email-routing/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/email_routing_settings
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/email_routing_rule
- https://developers.cloudflare.com/email-routing/email-workers/
