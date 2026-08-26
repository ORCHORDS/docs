# Terraform Cloudflare Access Policy Group Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A growing Cloudflare Zero Trust deployment has 30+ Access applications. Each application
policy repeats the same email list, identity-provider group, or country block. When a
new hire joins, the same email must be added to 30 separate policy rules. When Access
Groups are not used, drift is inevitable — some applications get the update and others
do not. The solution is to extract reusable `cloudflare_access_group` resources and
reference them by ID in every policy that needs the same membership rule, so a single
`terraform apply` propagates changes everywhere.

## Context

Cloudflare Access Groups are reusable rule sets with three sections:

- **include** — union of identities that may pass through the group
- **exclude** — identities explicitly denied even if they appear in `include`
- **require** — identities that must _all_ be present (AND logic)

A `cloudflare_access_policy` rule can reference an Access Group via
`include { group = [cloudflare_access_group.foo.id] }`. This is not the same as an
IdP group claim — an Access Group is a Cloudflare-side abstraction that can contain
email lists, SAML attribute assertions, IdP group IDs, geo blocks, service tokens, and
more, all composed into a single reusable identity boundary.

Groups are account-scoped, so any application in the account can reference them.

## 1. Provider Setup

```hcl
# versions.tf
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

provider "cloudflare" {
  api_token = <redacted-secret>
}

variable "cloudflare_api_token"  { type = string; sensitive = true }
variable "cloudflare_account_id" { type = string }
variable "zone_id"               { type = string }
```

## 2. Defining Reusable Groups

```hcl
# groups.tf

# --- Engineering team: email list + Okta group
resource "cloudflare_access_group" "engineering" {
  account_id = var.cloudflare_account_id
  name       = "Engineering Team"

  include {
    email = [
      "alice@example.com",
      "bob@example.com",
      "carol@example.com",
    ]

    # Also accept anyone with the Okta "engineering" group claim
    okta {
      identity_provider_id = var.okta_idp_id
      name                 = ["engineering"]
    }
  }
}

# --- Contractors: service token only, expires via policy
resource "cloudflare_access_group" "contractors" {
  account_id = var.cloudflare_account_id
  name       = "Contractors"

  include {
    service_token = [
      cloudflare_access_service_token.contractor_a.id,
      cloudflare_access_service_token.contractor_b.id,
    ]
  }

  # Deny access from high-risk countries even if the service token is valid
  exclude {
    geo = ["CN", "RU", "KP", "IR"]
  }
}

# --- Emergency break-glass: single email, require MFA
resource "cloudflare_access_group" "break_glass" {
  account_id = var.cloudflare_account_id
  name       = "Break Glass"

  include {
    email = ["sre-oncall@example.com"]
  }

  require {
    mfa { }
  }
}

# --- All internal staff: corporate IdP, office IP fallback
resource "cloudflare_access_group" "internal_staff" {
  account_id = var.cloudflare_account_id
  name       = "Internal Staff"

  include {
    saml {
      attribute_name  = "department"
      attribute_value = "engineering"
      identity_provider_id = var.saml_idp_id
    }
    saml {
      attribute_name  = "department"
      attribute_value = "product"
      identity_provider_id = var.saml_idp_id
    }
    # Office egress IPs as fallback for devices not enrolled in IdP
    ip = var.office_ip_ranges
  }
}
```

## 3. Composing Groups into Access Policies

```hcl
# policies.tf

# Internal dashboard — engineers and internal staff, no contractors
resource "cloudflare_access_application" "internal_dashboard" {
  account_id       = var.cloudflare_account_id
  name             = "Internal Dashboard"
  domain           = "dash.${var.domain}"
  session_duration = "8h"
}

resource "cloudflare_access_policy" "internal_dashboard_policy" {
  application_id = cloudflare_access_application.internal_dashboard.id
  account_id     = var.cloudflare_account_id
  name           = "Allow Engineering and Internal Staff"
  precedence     = 1
  decision       = "allow"

  include {
    group = [
      cloudflare_access_group.engineering.id,
      cloudflare_access_group.internal_staff.id,
    ]
  }
}

# Staging API — engineers + contractors, plus break-glass
resource "cloudflare_access_application" "staging_api" {
  account_id       = var.cloudflare_account_id
  name             = "Staging API"
  domain           = "api-staging.${var.domain}"
  session_duration = "4h"
}

resource "cloudflare_access_policy" "staging_api_policy" {
  application_id = cloudflare_access_application.staging_api.id
  account_id     = var.cloudflare_account_id
  name           = "Allow Engineering, Contractors, Break-glass"
  precedence     = 1
  decision       = "allow"

  include {
    group = [
      cloudflare_access_group.engineering.id,
      cloudflare_access_group.contractors.id,
      cloudflare_access_group.break_glass.id,
    ]
  }
}
```

## 4. Variables-Driven Email Lists for Large Teams

When engineer headcount is high, manage email lists in `terraform.tfvars` rather than
hard-coding them in the resource:

```hcl
# variables.tf
variable "engineering_emails" {
  type    = list(string)
  default = []
}

# groups.tf (revised)
resource "cloudflare_access_group" "engineering" {
  account_id = var.cloudflare_account_id
  name       = "Engineering Team"

  include {
    email = var.engineering_emails
    okta {
      identity_provider_id = var.okta_idp_id
      name                 = ["engineering"]
    }
  }
}
```

```hcl
# terraform.tfvars
engineering_emails = [
  "alice@example.com",
  "bob@example.com",
  "carol@example.com",
  "david@example.com",
]
```

Adding a new hire is now a one-line change to `terraform.tfvars` + `terraform apply`.

## 5. Importing Existing Groups

```bash
# List existing group IDs
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/access/groups" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {id, name}'

# Import into Terraform state
terraform import cloudflare_access_group.engineering \
  "${ACCOUNT_ID}/${GROUP_ID}"
```

## 6. Output Group IDs for Cross-Module Reference

```hcl
# outputs.tf
output "group_engineering_id"    { value = cloudflare_access_group.engineering.id }
output "group_contractors_id"    { value = cloudflare_access_group.contractors.id }
output "group_internal_staff_id" { value = cloudflare_access_group.internal_staff.id }
output "group_break_glass_id"    { value = cloudflare_access_group.break_glass.id }
```

Reference in another root module:

```hcl
data "terraform_remote_state" "access_groups" {
  backend = "s3"
  config  = { bucket = "tf-state", key = "access-groups/terraform.tfstate", region = "us-east-1" }
}

resource "cloudflare_access_policy" "some_other_app" {
  # ...
  include {
    group = [data.terraform_remote_state.access_groups.outputs.group_engineering_id]
  }
}
```

## Anti-patterns

- **Duplicating email lists across policies** — adding the same 50 emails to 10
  individual policies means 10 places to update on every personnel change. Centralise
  into `cloudflare_access_group` and reference the ID.
- **Putting `require { mfa {} }` only on some policies** — MFA enforcement should be
  a group-level `require` block applied to all privileged groups, not an optional
  per-application decision that can be forgotten.
- **Mixing include logic between the group and the policy** — if a group's `include`
  already contains emails and IdP groups, don't repeat them in the policy's `include`
  as well. The duplication creates confusion about the effective rule.
- **Creating groups without names that reflect their boundary** — "Group 1" or
  "Temp" names make the Terraform plan unreadable. Use names that describe the membership
  intent, e.g., "Engineering Team (Okta + email)" or "Contractors — Service Token Only".

## Gotchas

- Deleting an Access Group that is still referenced by a policy returns a 400 error.
  Always remove or update all policy references before destroying the group.
- The `group` field inside a policy's `include` block takes a list of group **IDs**, not
  group names. Using the wrong attribute causes a 422 on `apply`.
- Access Groups do not support nested groups (a group containing another group). If you
  need a hierarchy, compose the same IdP claim or email list into each group separately.
- When `email_domain` is used instead of `email`, the domain match is case-sensitive on
  the API side but Terraform lowercases input. Ensure email domains in tfvars are
  already lowercase.
- Changes to a group propagate immediately to all applications that reference it — no
  deployment step required, but also no rollback window.

## Verification

```bash
# Confirm group membership via API
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/access/groups/${GROUP_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.include'

# List all policies referencing a group (manual cross-reference)
terraform state list | grep cloudflare_access_policy | while read r; do
  terraform state show "$r" | grep -l "${GROUP_ID}" && echo "Referenced by: $r"
done

# Test access for a known user (Zero Trust dashboard → Access → Logs)
open "https://dash.cloudflare.com/${ACCOUNT_ID}/zero-trust/access/logs"
```

## Related

- `terraform-cloudflare-access-application-policy.md` — application-level policy structure
- `cloudflare-access-self-service-app-provisioning.md` — self-service app onboarding
- `pulumi-cloudflare-zero-trust-access-policy-automation.md` — Pulumi equivalent
- `cloudflare-zero-trust-staging-prod-isolation.md` — multi-environment isolation patterns
- `zero-trust-network-access.md` — ZTNA fundamentals

## Sources

- `cloudflare_access_group` resource: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/access_group
- Access Group API: https://developers.cloudflare.com/api/operations/access-groups-list-access-groups
- Zero Trust policy composition: https://developers.cloudflare.com/cloudflare-one/policies/access/
