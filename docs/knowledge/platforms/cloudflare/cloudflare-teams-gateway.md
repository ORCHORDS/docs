# cloudflare-teams-gateway

**Issue:** Configuring Cloudflare Gateway (DNS/HTTP filtering) within Cloudflare One / Zero Trust
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Gateway is the DNS and HTTP proxy layer of Cloudflare One (Zero Trust). It filters outbound traffic from enrolled devices, enforces content policies, blocks malware domains, and can log all DNS and HTTP activity.

## Pattern / Solution

**DNS filtering setup:**
1. Zero Trust → Gateway → DNS Locations → Add Location.
2. Name it (e.g. "Office Network"), optionally pin a source IP.
3. Use the generated DNS resolver IPs:
   - Primary: `172.64.36.1`
   - Secondary: `172.64.36.2`
   - DoH: `https://<team>.cloudflare-gateway.com/dns-query`
4. Configure routers/devices to use these DNS servers.

**HTTP policies:**
```
Zero Trust → Gateway → Firewall Policies → HTTP
```
Example policy (block social media for unmanaged devices):
- Condition: `Application: in [Facebook, Instagram, TikTok]`
  AND `Device Posture: not [Corporate Device]`
- Action: **Block** (show block page)

**DNS policies:**
```
Zero Trust → Gateway → Firewall Policies → DNS
```
Example: Block malware and adult content:
- `Security Threats: in [Malware, Phishing]` → Block
- `Content Categories: in [Adult Themes]` → Block

**Enabling Gateway via WARP Client:**
1. Zero Trust → Settings → WARP Client → Device Enrollment.
2. Deploy WARP to devices via MDM (Jamf, Intune, etc.) with:
```json
{
  "organization": "myteam",
  "service_mode": "proxy",
  "onboarding": false
}
```

**Logging to R2:**
```
Zero Trust → Logs → Logpush → Add Job → HTTP / DNS
Destination: R2 bucket
```

**Bypass for specific domains (split tunnel):**
```
Zero Trust → Settings → WARP Client → Profile Settings → Split Tunnels
Add exclusion: internal.company.com → Route via Local Network
```

## Gotchas
- Gateway DNS filtering only works for **enrolled devices** using WARP or the configured DNS resolvers — unmanaged devices bypass it.
- HTTPS inspection (HTTP policy) requires installing the **Cloudflare root certificate** on managed devices; without it, TLS inspection is not possible.
- DoH (DNS-over-HTTPS) cannot be filtered by Gateway unless the device routes traffic through WARP.
- Gateway does not replace firewall rules — it is a layer 7 proxy, not a network firewall.
- Policies are evaluated top-to-bottom; order matters. Place allow rules before block rules for specific domains.
- Free Zero Trust plan allows up to 50 users; paid plans scale further.

## Related
- `zero-trust-access.md`
- `zero-trust-device-posture.md`
- `cloudflare-access-jwt-validation.md`
