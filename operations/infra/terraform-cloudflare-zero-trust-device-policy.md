# Terraform: Cloudflare Zero Trust Device Posture Policies

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to enforce device health checks — OS version, disk encryption, EDR presence — before granting access to internal applications via Cloudflare Access, and want those policies version-controlled in Terraform.

## Context
Cloudflare Zero Trust device posture rules integrate with the WARP client and third-party MDM/EDR platforms (CrowdStrike, Intune, Jamf, SentinelOne). Posture rules evaluate device attributes at Access policy evaluation time and can be composed with user identity rules. Terraform's `cloudflare_device_posture_rule` and `cloudflare_device_posture_integration` resources manage the full lifecycle via the `cloudflare/cloudflare` provider (≥ 4.x).

## Defining a Posture Integration
Integrations connect Cloudflare to a third-party MDM or EDR API so it can pull device health signals.

```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

variable "cf_account_id" { type = string }

# CrowdStrike Falcon integration — pulls ZTA score per device
resource "cloudflare_device_posture_integration" "crowdstrike" {
  account_id = var.cf_account_id
  name       = "crowdstrike-zta"
  type       = "crowdstrike_s2s"
  interval   = "10m"

  config {
    api_url       = "https://api.crowdstrike.com"
    auth_url      = "https://api.crowdstrike.com/oauth2/token"
    client_id     = var.crowdstrike_client_id
    client_secret = <redacted-secret>  # sensitive; use TF_VAR or Vault
  }
}
```

The `interval` controls how often Cloudflare re-polls the integration. Shorter intervals increase freshness but count against API quota.

## Defining Posture Rules
Each rule tests a specific device attribute. Rules are later referenced inside Access policies.

```hcl
# Rule 1: require disk encryption
resource "cloudflare_device_posture_rule" "disk_encryption" {
  account_id  = var.cf_account_id
  name        = "disk-encryption-required"
  type        = "disk_encryption"
  description = "FileVault (macOS) or BitLocker (Windows) must be enabled"
  schedule    = "5m"    # how often WARP re-evaluates on the device
  expiration  = "30m"   # result TTL if WARP is offline

  match {
    platform = "mac"
  }
  match {
    platform = "windows"
  }

  input {
    require_all = true  # all matched volumes must be encrypted
  }
}

# Rule 2: minimum OS version
resource "cloudflare_device_posture_rule" "os_version_macos" {
  account_id  = var.cf_account_id
  name        = "macos-version-min"
  type        = "os_version"
  description = "macOS must be Sequoia 15.4 or newer"
  schedule    = "1h"
  expiration  = "8h"

  match {
    platform = "mac"
  }

  input {
    version          = "15.4.0"
    operator         = ">="
    version_operator = ">="
  }
}

# Rule 3: CrowdStrike ZTA score threshold
resource "cloudflare_device_posture_rule" "crowdstrike_score" {
  account_id  = var.cf_account_id
  name        = "crowdstrike-zta-score"
  type        = "crowdstrike_s2s"
  description = "CrowdStrike ZTA score must be ≥ 70"
  schedule    = "10m"
  expiration  = "30m"

  input {
    connection_id = cloudflare_device_posture_integration.crowdstrike.id
    score         = 70
    operator      = ">="
  }
}
```

## Wiring Rules into an Access Policy

```hcl
# Access application — internal admin panel
resource "cloudflare_zero_trust_access_application" "admin_panel" {
  account_id       = var.cf_account_id
  name             = "Admin Panel"
  domain           = "admin.internal.example.com"
  type             = "self_hosted"
  session_duration = "4h"
}

# Access policy: require identity AND healthy device
resource "cloudflare_zero_trust_access_policy" "admin_allow" {
  account_id     = var.cf_account_id
  application_id = cloudflare_zero_trust_access_application.admin_panel.id
  name           = "Allow corporate devices"
  decision       = "allow"
  precedence     = 1

  include {
    email_domain = ["example.com"]
  }

  require {
    device_posture = [
      cloudflare_device_posture_rule.disk_encryption.id,
      cloudflare_device_posture_rule.os_version_macos.id,
      cloudflare_device_posture_rule.crowdstrike_score.id,
    ]
  }
}

# Fallback policy: block everyone else
resource "cloudflare_zero_trust_access_policy" "admin_deny" {
  account_id     = var.cf_account_id
  application_id = cloudflare_zero_trust_access_application.admin_panel.id
  name           = "Block non-compliant"
  decision       = "deny"
  precedence     = 2

  include {
    everyone = true
  }
}
```

## Anti-patterns
- Omitting `expiration` — devices that go offline keep their last-evaluated result indefinitely, allowing stale posture to grant access
- Using `schedule = "1m"` on integration-backed rules — hammers the third-party API and can exceed Cloudflare's inbound rate limits
- Putting posture rules in `include` instead of `require` — `include` is OR-semantics; posture must go in `require` to be enforced
- Hardcoding `client_secret` in `.tf` files — always pass via `TF_VAR_` env vars or a Vault dynamic secret
- Forgetting `match { platform }` on OS-version rules — without it the rule applies to all platforms and will fail on OSes where the version format differs

## Gotchas
- The WARP client must be enrolled via the Cloudflare One dashboard or MDM before any posture rule can evaluate; Terraform cannot install WARP
- `cloudflare_device_posture_rule` IDs are UUIDs assigned by the API; reference them via `resource.id`, never hardcode
- Platform-specific rules (`mac`, `windows`, `linux`, `ios`, `android`, `chromeos`) are case-sensitive in the API; Terraform provider validates them
- Device posture is an Enterprise Zero Trust feature; check account entitlements before applying or `terraform apply` will return a 403
- Integration re-polling interval must be a multiple of 1 minute; fractional minute strings are rejected

## Verification
```bash
# List all posture rules in the account
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/devices/posture" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, type, schedule}'

# Check integration sync status
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/devices/posture/integration" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, type, interval}'

# Terraform plan in CI
terraform plan -var-file=prod.tfvars -out=tfplan
terraform show -json tfplan | jq '.resource_changes[] | select(.type | startswith("cloudflare_device_posture"))'
```

## Related
- `cloudflare-zero-trust-staging-prod-isolation.md` — environment separation for Zero Trust applications
- `terraform-cloudflare-access-application-policy.md` — Access application and policy management
- `terraform-cloudflare-access-group-policy-management.md` — Access group composition
- `cloudflare-mtls-client-certificates-terraform.md` — mTLS as an alternative/complement to device posture

## Sources
- https://developers.cloudflare.com/cloudflare-one/identity/devices/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/device_posture_rule
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/device_posture_integration
- https://developers.cloudflare.com/cloudflare-one/identity/devices/warp-client-checks/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/
