# Terraform Cloudflare Registrar Domain Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You registered a domain through Cloudflare Registrar and want to manage auto-renewal, WHOIS privacy, transfer lock, and registrant contact details as code. Manual changes through the dashboard are error-prone across a large portfolio and do not survive audits.

## Context

Cloudflare Registrar supports IaC management through the `cloudflare_registrar_domain` Terraform resource (provider ≥ 4.36). The resource is import-only for domains already registered — you cannot register a new domain through Terraform, only manage lifecycle settings of an existing one. Each domain must be imported before Terraform can manage it. WHOIS privacy is enabled by default for new Cloudflare registrations; Terraform surfaces it as a toggle so you can enforce it organisation-wide.

---

## Provider Setup

```hcl
# versions.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.36"
    }
  }
  required_version = ">= 1.9"
}

provider "cloudflare" {
  api_token = <redacted-secret>
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "account_id" {
  type = string
}
```

## Importing an Existing Domain

Domains cannot be created by Terraform — they must be imported first. Use `terraform import` or a Terraform `import` block (Terraform ≥ 1.5).

```hcl
# main.tf — import block (preferred, avoids shell escape issues)
import {
  to = cloudflare_registrar_domain.example_com
  id = "example.com"  # domain name is the resource ID
}

resource "cloudflare_registrar_domain" "example_com" {
  account_id  = var.account_id
  domain_name = "example.com"

  auto_renew    = true
  privacy       = true   # WHOIS privacy via Redacted for Privacy
  locked        = true   # transfer lock — prevents unauthorised registrar moves

  # Registrant contact — required if privacy = false
  # registrant_contact { ... }
}
```

Run `terraform plan` after adding the import block to preview the diff before `terraform apply`.

## Managing a Portfolio of Domains

```hcl
# variables.tf
variable "domains" {
  type = map(object({
    auto_renew = bool
    privacy    = bool
    locked     = bool
  }))
  default = {
    "example.com" = { auto_renew = true, privacy = true, locked = true }
    "example.net" = { auto_renew = true, privacy = true, locked = true }
    "legacy.io"   = { auto_renew = false, privacy = false, locked = false }
  }
}

# main.tf
resource "cloudflare_registrar_domain" "all" {
  for_each = var.domains

  account_id  = var.account_id
  domain_name = each.key
  auto_renew  = each.value.auto_renew
  privacy     = each.value.privacy
  locked      = each.value.locked
}

# Import blocks for each domain in the map
import {
  for_each = var.domains
  to       = cloudflare_registrar_domain.all[each.key]
  id       = each.key
}
```

## Registrant Contact Details (WHOIS privacy disabled)

```hcl
resource "cloudflare_registrar_domain" "contact_example" {
  account_id  = var.account_id
  domain_name = "contact-example.com"
  auto_renew  = true
  privacy     = false
  locked      = true

  registrant_contact {
    first_name   = "Platform"
    last_name    = "Team"
    email        = "domains@company.com"
    phone        = "+15555550100"
    address      = "123 Main St"
    city         = "San Francisco"
    state        = "CA"
    zip          = "94105"
    country      = "US"
    organization = "Acme Corp"
  }
}
```

## Expiry Alert with Terraform Output and Notification

```hcl
# Output expiry date for external monitoring
output "domain_expiry_dates" {
  value = {
    for k, v in cloudflare_registrar_domain.all : k => v.expires_at
  }
  description = "Domain expiry dates — feed into PagerDuty or Slack alerts"
}

# Notification policy for domain expiry (uses cloudflare_notification_policy)
resource "cloudflare_notification_policy" "domain_expiry" {
  account_id  = var.account_id
  name        = "domain-expiry-60d"
  description = "Alert 60 days before domain expiry"
  enabled     = true
  alert_type  = "expiring_service_token_alert"  # closest available; domain-specific type varies by plan

  email_integration {
    id   = cloudflare_notification_policy_webhooks.slack.id
    name = "slack-domains"
  }
}
```

## Drift Detection with CI

```yaml
# .github/workflows/domain-drift.yml
name: domain-drift-check
on:
  schedule:
    - cron: "0 9 * * 1"   # Monday 09:00 UTC
  workflow_dispatch:

jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.x"
      - name: terraform init
        run: terraform init
        working-directory: infra/registrar
        env:
          TF_VAR_cloudflare_api_token: ${{ secrets.CF_API_TOKEN }}
      - name: terraform plan — drift only
        run: terraform plan -detailed-exitcode -out=plan.tfplan
        working-directory: infra/registrar
        env:
          TF_VAR_cloudflare_api_token: ${{ secrets.CF_API_TOKEN }}
          TF_VAR_account_id: ${{ secrets.CF_ACCOUNT_ID }}
```

---

## Anti-patterns

- **Managing unimported domains**: Terraform will show a blank resource with no values until the domain is imported. Always import first.
- **Setting `privacy = false` without a registrant_contact block**: The apply succeeds but WHOIS will surface Cloudflare's contact details instead of yours.
- **Storing contact PII in plaintext tfvars**: Use SOPS or Vault to encrypt the `registrant_contact` block if committed to version control.
- **Disabling `locked` during routine operations**: Transfer lock should remain `true` unless an intentional transfer is underway.

## Gotchas

- `expires_at` is a read-only attribute — you cannot set it; Terraform shows it in the state after import.
- Auto-renewal requires a valid payment method in the Cloudflare account; Terraform will not surface payment failures.
- The resource ID is the bare domain name (e.g., `example.com`), not the zone ID.
- Changes to `registrant_contact` trigger a real WHOIS update at the registry, which may take up to 24 hours to propagate.
- API tokens need the **Registrar - Read** and **Registrar - Edit** permissions scoped to the account, not a zone.

## Verification

```bash
# Confirm Terraform sees the domain
terraform state show 'cloudflare_registrar_domain.example_com'

# Check live WHOIS to confirm privacy / lock status
whois example.com | grep -E "(Registrar|Registrant|Status|Expiry)"

# Cloudflare API — list registrar domains
curl -s https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/registrar/domains \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name, auto_renew, privacy, locked, expires_at}'
```

## Related

- `terraform-cloudflare-dns-zone-record-management.md`
- `terraform-cloudflare-notification-policy.md`
- `cloudflare-dns-api.md`
- `dns-ttl-strategy.md`

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/registrar_domain
- https://developers.cloudflare.com/registrar/
- https://developers.cloudflare.com/registrar/account-options/whois-redaction/
- https://developers.cloudflare.com/registrar/domain-transfers/transfer-lock/
