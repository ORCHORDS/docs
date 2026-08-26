# Cloudflare WARP Split Tunnel Configuration via Terraform

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case**: Your Zero Trust WARP deployment routes all traffic through Cloudflare by default, causing performance issues for SaaS tools (Zoom, Figma, Slack CDN) or internal high-bandwidth services. You need to declaratively manage split tunnel exclude/include lists per device profile group using Terraform, with per-environment overrides and a validation gate in CI.

**Context**: Cloudflare Zero Trust split tunnels are configured at the **Device Settings** policy level, not at the global account level. Each `cloudflare_device_settings_policy` resource in Terraform can include `exclude` entries (route these IPs/CIDRs/domains directly, bypass WARP tunnel) or operate in `include` mode (only tunnel listed routes). Different device profiles (e.g., "engineers", "contractors", "on-call") can have different tunnel policies. Terraform manages both the device profiles and their split tunnel entries.

---

## Resource Structure Overview

```hcl
# terraform/zero-trust-split-tunnel/variables.tf

variable "cloudflare_account_id" { type = string }

variable "engineer_exclude_routes" {
  type = list(object({ address = string, description = string }))
  default = [
    # SaaS video/voice — high bandwidth, low security risk
    { address = "18.64.0.0/14",      description = "Zoom US East" },
    { address = "162.247.37.0/24",   description = "Zoom US West" },
    { address = "0.zoom.us",         description = "Zoom domain" },
    { address = "slack-edge.com",    description = "Slack CDN" },
    { address = "figma.com",         description = "Figma" },
    # Internal high-bandwidth artifact store bypasses tunnel
    { address = "10.50.0.0/16",      description = "Internal artifact cache" },
  ]
}

variable "contractor_exclude_routes" {
  type = list(object({ address = string, description = string }))
  default = [
    # Contractors get minimal exclusions — only SaaS video
    { address = "0.zoom.us",       description = "Zoom domain" },
    { address = "18.64.0.0/14",    description = "Zoom US East" },
  ]
}
```

## Device Settings Policies with Split Tunnels

```hcl
# terraform/zero-trust-split-tunnel/main.tf

# Engineer device profile — WARP in exclude mode (tunnel everything except listed)
resource "cloudflare_device_settings_policy" "engineers" {
  account_id   = var.cloudflare_account_id
  name         = "engineers-policy"
  description  = "Full WARP for engineers with SaaS exclusions"
  precedence   = 10
  match        = "identity.groups.name == \"engineers\""
  enabled      = true

  # Exclude mode: listed routes bypass the tunnel
  tunnel_protocol          = "masque"
  service_mode_v2_mode     = "warp"
  service_mode_v2_port     = 0
  switch_locked            = true   # prevent users disabling WARP
  auto_connect             = 1      # reconnect after 1s disconnect
  captive_portal           = 180
  disable_auto_fallback    = false
  allow_mode_switch        = false
  support_url              = "https://help.internal/warp"

  dynamic "exclude" {
    for_each = var.engineer_exclude_routes
    content {
      address     = exclude.value.address
      description = exclude.value.description
    }
  }
}

# Contractor device profile — tighter policy
resource "cloudflare_device_settings_policy" "contractors" {
  account_id   = var.cloudflare_account_id
  name         = "contractors-policy"
  description  = "Restricted WARP for contractors"
  precedence   = 20
  match        = "identity.groups.name == \"contractors\""
  enabled      = true

  tunnel_protocol       = "masque"
  service_mode_v2_mode  = "warp"
  switch_locked         = true
  allow_mode_switch     = false

  dynamic "exclude" {
    for_each = var.contractor_exclude_routes
    content {
      address     = exclude.value.address
      description = exclude.value.description
    }
  }
}

# On-call engineers — include mode (only tunnel internal RFC-1918 + Zero Trust apps)
resource "cloudflare_device_settings_policy" "oncall" {
  account_id   = var.cloudflare_account_id
  name         = "oncall-include-policy"
  description  = "Include-mode tunnel for on-call engineers — only internal traffic tunneled"
  precedence   = 5
  match        = "identity.groups.name == \"oncall\" and device.os_version > \"14.0\""
  enabled      = true

  tunnel_protocol       = "masque"
  service_mode_v2_mode  = "warp"
  switch_locked         = true

  # Include mode: only listed routes go through tunnel
  include {
    address     = "10.0.0.0/8"
    description = "Internal RFC-1918"
  }
  include {
    address     = "172.16.0.0/12"
    description = "Internal RFC-1918"
  }
  include {
    address     = "192.168.0.0/16"
    description = "Internal RFC-1918"
  }
  include {
    address     = "*.internal.example.com"
    description = "All internal services"
  }
}
```

## Local Fallback Domains (DNS Bypass)

```hcl
# terraform/zero-trust-split-tunnel/fallback-domains.tf

# Domains resolved locally (not through Cloudflare Gateway DNS)
# Applied globally, not per-policy — affects all WARP profiles
resource "cloudflare_fallback_domain" "local_domains" {
  account_id = var.cloudflare_account_id

  domains = [
    {
      suffix      = "corp.internal"
      description = "Internal corporate DNS"
      dns_server  = ["10.0.0.53", "10.0.1.53"]
    },
    {
      suffix      = "local"
      description = "mDNS / Bonjour"
      dns_server  = []
    },
    {
      suffix      = "home.arpa"
      description = "Local home network"
      dns_server  = []
    },
  ]
}
```

## CI Validation: Checking for Reserved Range Conflicts

```typescript
// scripts/validate-split-tunnels.ts
// Run in CI before terraform apply to catch common misconfigurations

import { execSync } from "child_process";

interface ExcludeEntry { address: string; description: string; }

// These should NEVER be excluded — they are required for WARP to function
const PROTECTED_RANGES = [
  "100.96.0.0/12",   // WARP internal routing
  "fd01:db8::/32",   // WARP IPv6
];

function validateExcludes(entries: ExcludeEntry[]): string[] {
  const errors: string[] = [];
  for (const entry of entries) {
    if (PROTECTED_RANGES.some((r) => r === entry.address)) {
      errors.push(`BLOCKED: ${entry.address} is a protected WARP range — removing it breaks connectivity`);
    }
    // Warn if excluding all RFC-1918 (defeats Zero Trust)
    if (entry.address === "10.0.0.0/8" || entry.address === "192.168.0.0/16") {
      errors.push(`WARNING: Excluding ${entry.address} bypasses Zero Trust for all internal services`);
    }
  }
  return errors;
}

// Read terraform plan output and validate
const plan = JSON.parse(execSync("terraform show -json tfplan.out").toString());
const policies = plan.planned_values?.root_module?.resources?.filter(
  (r: { type: string }) => r.type === "cloudflare_device_settings_policy"
) ?? [];

let hasErrors = false;
for (const policy of policies) {
  const excludes: ExcludeEntry[] = policy.values?.exclude ?? [];
  const errors = validateExcludes(excludes);
  if (errors.length > 0) {
    console.error(`Policy ${policy.values?.name}:`);
    errors.forEach((e) => console.error(`  ${e}`));
    if (errors.some((e) => e.startsWith("BLOCKED"))) hasErrors = true;
  }
}

if (hasErrors) process.exit(1);
console.log("Split tunnel validation passed.");
```

## GitHub Actions Gate

```yaml
# .github/workflows/warp-split-tunnel-validate.yml
name: Validate WARP Split Tunnels

on:
  pull_request:
    paths:
      - 'terraform/zero-trust-split-tunnel/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init
        working-directory: terraform/zero-trust-split-tunnel
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_ZERO_TRUST_TOKEN }}

      - name: Terraform Plan
        run: terraform plan -out=tfplan.out
        working-directory: terraform/zero-trust-split-tunnel

      - name: Validate split tunnel entries
        run: npx ts-node ../../scripts/validate-split-tunnels.ts
        working-directory: terraform/zero-trust-split-tunnel
```

---

**Anti-patterns**:
- Excluding `100.96.0.0/12` from the tunnel — this is WARP's own internal CGNAT range; excluding it breaks the tunnel itself.
- Using a single global device policy instead of per-group profiles — loses the ability to tighten policy for contractors or untrusted devices.
- Mixing exclude and include entries in the same policy — Cloudflare Device Settings policies operate in one mode or the other; mixing silently uses whichever the provider serializes last.
- Excluding all of `10.0.0.0/8` in the engineer profile to "fix performance" — bypasses Zero Trust enforcement for all internal services and removes audit logging.
- Not setting `switch_locked = true` on contractor policies — users can toggle WARP off and bypass all Zero Trust controls.

**Gotchas**:
- `precedence` on `cloudflare_device_settings_policy` is an integer where **lower numbers win** — set the most specific (on-call) policy to precedence 5, general engineer to 10, contractor to 20.
- Split tunnel `exclude` with a domain (e.g., `slack-edge.com`) only bypasses DNS resolution and routing for that domain — IP ranges used by that domain but not excluded may still route through the tunnel.
- Fallback domains (local DNS bypass) are a separate resource from split tunnels; a domain in `exclude` still queries Cloudflare Gateway DNS unless it is also in `fallback_domain`.
- The Terraform Cloudflare provider requires the account-level Zero Trust organization to already exist before device policy resources can be created — bootstrap with the `cloudflare_teams_account` resource first.
- `tunnel_protocol = "masque"` (HTTP/3-based) requires WARP client 2024.x+; older clients fall back to WireGuard silently.

**Verification**:
```bash
# List all device policies and their precedence
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/devices/policies" \
  | jq '.result[] | {name, precedence, match, enabled}'

# Check exclude entries for a specific policy
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/devices/policy/<policy-id>/exclude" \
  | jq '.result[] | {address, description}'

# From a test device: confirm split tunnel is working
warp-cli tunnel stats
ip route show table 65423   # WARP tunnel routes on Linux
```

**Related**:
- `terraform-cloudflare-zero-trust-device-policy.md`
- `cloudflare-zero-trust-staging-prod-isolation.md`
- `zero-trust-network-access.md`
- `cloudflare-tunnel-private-services.md`

**Sources**:
- https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/configure-warp/route-traffic/split-tunnels/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/device_settings_policy
- https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/configure-warp/warp-settings/
