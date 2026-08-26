# Cloudflare Zero Trust WARP Client Policies

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You roll out the WARP client to company devices and immediately hit problems: developers complain that localhost traffic is being tunnelled (breaking Docker and local dev servers), certain SaaS apps break behind the Gateway proxy, and mobile users on metered connections report unexpected data usage. You need fine-grained control over what traffic WARP captures and how the client behaves per user segment.

---

## Context

The Cloudflare WARP client is the Zero Trust network agent. It terminates a WireGuard tunnel from the device to Cloudflare's edge, routing selected traffic through Cloudflare Gateway for DNS filtering, HTTP inspection, and network policy enforcement. The client is configurable through **Device Settings** profiles in the Zero Trust dashboard under **Settings → WARP Client**.

A **WARP Client Settings profile** bundles:
- Which traffic is routed through the tunnel (split tunnel rules)
- Local Domain Fallback rules (DNS handled locally)
- Device posture check requirements
- Service mode (Gateway with WARP / Gateway with DoH / Proxy / off)
- TLS decryption and certificate install settings

Profiles are ordered. Cloudflare evaluates them top-to-bottom and applies the **first matching profile** to each device session. Users with no matching profile fall through to the **Default** profile.

---

## Profile Matching: User Identity and Device Posture

Profiles match on:
- **User identity** — IdP group membership (Google, Okta, Azure AD groups)
- **Email** or **email domain**
- **Device posture checks** — OS version, serial number, domain join, disk encryption
- **OS family** — Windows / macOS / Linux / iOS / Android

```
Zero Trust dashboard → Settings → WARP Client → Device Settings → Create profile

Match criteria example:
  - Include: Groups contains "engineering"
  - Include: OS Family = macOS
  - Exclude: Posture check: Disk encrypted = false
```

This lets you send all engineers on encrypted Macs through Gateway with full HTTPS inspection, while contractors get a lighter profile with DoH only.

---

## Split Tunnel Configuration

Split tunnel rules control which IP ranges and domains bypass the WARP tunnel. Two modes:

### Include-only mode (Tunnel specified traffic)

Only traffic matching the include list goes through the tunnel. Everything else uses the local network stack. Best for remote workers who need corporate resources without routing all personal traffic through Cloudflare.

```
Mode: Include only
Include ranges:
  10.0.0.0/8          ← Internal RFC1918 ranges
  172.16.0.0/12
  192.168.0.0/16
  100.64.0.0/10       ← CGNAT (important for some ISPs)

Include domains:
  corp.example.com
  *.internal.example.com
```

### Exclude mode (Bypass specified traffic)

All traffic goes through the tunnel **except** what you list. Safer for compliance — nothing leaks unless explicitly excluded.

```
Mode: Exclude
Exclude ranges (defaults that should stay excluded):
  127.0.0.0/8         ← Loopback
  ::1/128
  169.254.0.0/16      ← Link-local
  224.0.0.0/4         ← Multicast
  fe80::/10

Exclude for developer ergonomics:
  100.64.0.0/10       ← Tailscale / CGNAT (if used alongside WARP)

Exclude domains for SaaS bypass:
  zoom.us             ← Latency-sensitive video
  teams.microsoft.com
  *.slack-edge.com
```

---

## Local Domain Fallback

Domains in the Local Domain Fallback list are resolved by the device's local DNS resolver, bypassing Cloudflare's DNS resolver (`100.64.0.1` inside the tunnel). Use this for:
- Internal Active Directory domains (`corp.local`, `ad.company.com`)
- mDNS names (`.local`)
- Development domains served by a local resolver

```
Local Domain Fallback:
  corp.local          → 192.168.1.1 (on-premise DNS)
  ad.company.com      → 10.0.0.5
  *.test              → (system resolver)
```

Without this, corporate AD lookups fail inside the tunnel because Cloudflare's resolver does not know your private zones.

---

## Configuring Profiles via Terraform

```hcl
# profiles.tf
resource "cloudflare_device_settings_policy" "engineering" {
  account_id  = var.cf_account_id
  name        = "Engineering — Mac"
  precedence  = 10
  enabled     = true

  match = "identity.groups.name == \"engineering\" and os.platform == \"mac\""

  service_mode_v2_mode = "warp"          # full tunnel + Gateway
  allow_mode_switch    = false           # lock users to this mode
  captive_portal       = 180            # seconds before showing portal page
  disable_auto_fallback = false

  # Enable certificate inspection (requires cert deployed to devices)
  tls_decrypt_enabled                   = true
  support_url                           = "https://it.example.com/warp"
}

resource "cloudflare_device_settings_policy" "contractors" {
  account_id  = var.cf_account_id
  name        = "Contractors — DNS only"
  precedence  = 20
  enabled     = true

  match = "identity.groups.name == \"contractors\""

  service_mode_v2_mode = "gateway_proxy_udp"  # Gateway with DoH only
  allow_mode_switch    = false
}

resource "cloudflare_split_tunnel" "engineering_includes" {
  account_id  = var.cf_account_id
  policy_id   = cloudflare_device_settings_policy.engineering.id
  mode        = "include"

  tunnels = [
    { address = "10.0.0.0/8",        description = "Corporate RFC1918" },
    { address = "172.16.0.0/12",     description = "Corporate RFC1918" },
    { host    = "corp.example.com",  description = "Corporate portal" },
  ]
}

resource "cloudflare_local_domain_fallback" "engineering" {
  account_id = var.cf_account_id
  policy_id  = cloudflare_device_settings_policy.engineering.id

  domains = [
    { suffix = "corp.local",      description = "AD forest" },
    { suffix = "ad.example.com",  description = "AD domain" },
  ]
}
```

---

## WARP Service Modes

| Mode | What it does | Use case |
|------|-------------|---------|
| `warp` (Gateway with WARP) | Full WireGuard tunnel; DNS + HTTP filtering | Default for managed devices |
| `gateway_proxy_udp` (Gateway with DoH) | DNS-over-HTTPS only; no L3/L4 inspection | Contractors, BYOD |
| `proxy` | Local SOCKS5 proxy on port 40000 | Apps that support proxy config explicitly |
| `off` | Tunnel disabled | Emergency break-glass |

Allow mode switching only for IT admins. Lock all other profiles with `allow_mode_switch = false`.

---

## Posture-Gated Profile Escalation

Combine posture checks with profile matching to gate elevated access:

```hcl
resource "cloudflare_device_posture_rule" "disk_encrypt" {
  account_id  = var.cf_account_id
  name        = "Disk Encryption Check"
  type        = "disk_encryption"

  match { platform = "mac" }
  input {
    require_all = true
    check_disks = []
  }
  schedule = "1h"
  expiration = "90m"
}

resource "cloudflare_device_settings_policy" "high_trust" {
  account_id = var.cf_account_id
  name       = "High Trust — Encrypted Mac"
  precedence = 5
  enabled    = true

  # Only matches if posture rule passes AND user is in admin group
  match = "any(identity.groups.name[*] == \"admins\") and any(device_posture.checks.passed[*] == \"${cloudflare_device_posture_rule.disk_encrypt.id}\")"

  service_mode_v2_mode = "warp"
  tls_decrypt_enabled  = true
}
```

---

## Anti-patterns

- **Putting split tunnel includes/excludes at the global Default profile level.** If you exclude `10.0.0.0/8` globally, a new named profile that should include it for engineering must explicitly override it. Keep the Default profile minimal — it is your fallback for unmanaged devices.
- **Adding SaaS domains to Local Domain Fallback instead of Split Tunnel.** LDF only controls DNS resolution. If you want traffic itself to bypass the tunnel (for latency), you must add the IP ranges or hostnames to the Split Tunnel exclude list. Adding them only to LDF resolves DNS locally but still routes packets through the tunnel.
- **Enabling TLS decryption without deploying the Cloudflare root certificate.** HTTPS inspection requires the Cloudflare TLS CA to be in the device trust store. Without it, every HTTPS site breaks with a certificate error. Use MDM (Jamf, Intune, Mosyle) to push the cert before enabling decryption.
- **Setting precedence values with no gaps.** Use multiples of 10 (10, 20, 30) so you can insert profiles between existing ones without renumbering everything.

---

## Gotchas

1. **Precedence conflicts.** Two profiles with the same precedence number produce undefined ordering. Cloudflare's UI warns about this, but the API does not block it. Always verify ordering in the dashboard after Terraform applies.
2. **IPv6 exclusions.** The default profile does not exclude `::1/128` or `fe80::/10` from the tunnel. If devices use IPv6 loopback for local services, add these to the exclude list or those services break.
3. **Captive portal detection.** On metered hotel / coffee-shop WiFi, WARP must release the tunnel to allow the captive portal flow. The `captive_portal` value (seconds to wait for internet before showing the portal) should be at least 180. Setting it too low causes WARP to drop and re-tunnel repeatedly.
4. **Per-user vs. per-device profiles.** Profiles match against the logged-in user identity. If a device is shared (kiosk) or used as a service account machine, user-identity-based matching may produce unexpected profile assignments. Use posture rules (serial number, machine certificate) for device-centric assignment.
5. **iOS and Android exclude mode vs. include mode.** Mobile WARP clients default to always-on in some MDM configurations. Include-only mode is strongly preferred on mobile to avoid routing all cellular data through the tunnel — which degrades battery life and performance on metered plans.
6. **Local Domain Fallback changes take effect on the next WARP registration, not immediately.** After a Terraform apply, devices poll for updated settings every few minutes. For urgent changes, ask users to toggle WARP off and on.

---

## Verification

```bash
# Check which profile a device received (Cloudflare API)
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/devices/posture/integration" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq .

# From the device itself (macOS / Linux): inspect WARP status
warp-cli status
warp-cli settings

# Check current split tunnel rules applied to this device session
warp-cli split-tunnel list

# Trigger an immediate policy refresh
warp-cli disconnect && warp-cli connect
```

Zero Trust dashboard validation path:

```
Zero Trust → Settings → WARP Client → Device Settings
→ Select profile → Preview matched devices
→ Compare with expected user/device list
```

---

## Related

- `zero-trust-access.md` — Access policies that gate app-level entry (complements WARP network-level)
- `zero-trust-device-posture.md` — Posture check types and integration with MDM
- `cloudflare-teams-gateway.md` — DNS filtering policies applied to tunnelled traffic
- `zero-trust-scim-deprovisioning-and-group-policy.md` — Keeping IdP groups in sync
- `cloudflare-access-zero-trust-service-tokens.md` — Machine-to-machine access without WARP

---

## Sources

- WARP client documentation: https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/
- Device Settings profiles: https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/configure-warp/device-settings/
- Split Tunnels: https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/configure-warp/route-traffic/split-tunnels/
- Local Domain Fallback: https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/configure-warp/route-traffic/local-domains/
- Terraform Cloudflare provider — device policies: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/device_settings_policy
