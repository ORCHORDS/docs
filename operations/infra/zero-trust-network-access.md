# zero-trust-network-access

**Issue:** Migrating from flat network + VPN perimeter to zero-trust access (ZTNA) without breaking production or recreating a VPN with extra steps
**Date:** 2026-08-13
**Status:** documented

## Symptom / Context
"Network location equals trust" stopped working: contractors need granular app access, workers move networks constantly, and lateral movement after one phishing hit is the #1 breach amplifier. Classic symptom: an audit finds a single compromised laptop in the VPN subnet can reach the database admin port, the metrics dashboard, and the CI runner — because the firewall allows "10.0.0.0/8 → 10.0.5.0/24".

Zero trust inverts the model: every request is authenticated, authorized, and encrypted per-connection, regardless of network. Identity (user + device posture), not IP, is the perimeter.

## Pattern / Solution
**Core pillars:** identity-aware proxy per app (not per network), device posture checks, short-lived credentials, deny-by-default segmentation, and continuous verification.

**Typical target architecture:**
```
User/Device
  → Identity provider (SSO: OIDC/SAML) ─┐
  → Device agent (posture: disk encryption,  →  ZTNA broker / identity-aware proxy
    patch level, EDR running)            ┘        │
                                               mTLS to origin
                                                 │
                                          App (behind connector, no inbound ports)
```

**Rules that make it zero trust rather than renamed VPN:**
1. One identity per application, not one network tunnel granting all
2. Policy is user/group + device posture + app, evaluated per session
3. No inbound listening ports on origins — outbound-only connectors (Cloudflare Tunnel, Tailscale Funnel inverted model, Zscaler connector)
4. mTLS or wrapped TLS end-to-end; internal plaintext is a finding
5. Session TTLs measured in minutes/hours, not days

**Policy-as-code example (scorecard style, works for any ZTNA product):**
```yaml
policy: prod-database-admin
effect: allow
subjects:
  groups: [sre-oncall]
  device_posture:
    disk_encrypted: true
    os_version: ">= 4471"        # patch floor
    edr_healthy: true
actions: [connect]
resources: [tcp/5432@pg-prod.internal]
conditions:
  window: business_hours + oncall_rotation
  mfa_recent: true               # step-up within last 8h
session_ttl: 60m
```

**Verification — continuously test that deny works:**
```bash
# From an unenrolled device, everything must fail closed
curl -v https://app.internal.example.com      # expect 403/no route, never 200
# From enrolled device without group membership
ztna connect app.internal.example.com         # expect policy denial, logged
```

**Migration sequence that avoids outages:**
1. Deploy ZTNA in monitor/parallel mode next to VPN; keep both working
2. Move read-only internal tools first (wikis, dashboards)
3. Then CI, then admin panels, databases last
4. Set VPN to per-app mode (not full tunnel) as an intermediate step
5. Cut over per-app; keep VPN break-glass for exactly one quarter, then remove it — a VPN left "just in case" becomes the permanent bypass

## Gotchas
- ZTNA that ships a full-tunnel client with an allow-all policy is just a VPN with worse latency. The win is per-app policy; if you cannot express "this group → this app on this port," you bought nothing.
- Non-human identities: cron jobs, service-to-service calls, and legacy appliances have no SSO login. Plan workload identity (SPIFFE/mTLS, or scoped tokens) first or the migration stalls at week two.
- UDP/thick clients (SSH, RDP, VoIP, database GUIs) perform badly over some brokers. Test the actual protocols your ops team uses, not just HTTP apps.
- Device posture checks on Linux are weak in most products (macOS/Windows get the deep checks). A Linux laptop can become the trusted-device loophole.
- Latency: broker adds a hop. Users in regions far from the nearest ZTNA edge notice 50-150 ms additions on chatty protocols. Pick providers with edges near your users.
- DNS still leaks topology. If internal DNS answers resolve publicly, attackers map you regardless of access controls. Use split-horizon DNS tied to the ZTNA context.
- Audit both sides: successful connections AND denied attempts. Denials that suddenly stop arriving for a previously-noisy app usually mean someone widened a rule to "unblock" a ticket.

## Related
- `network-segmentation-strategy.md`
- `bastion-host-pattern.md`
- `policy-as-code-opa-kyverno.md`
- `service-mesh-ambient-sidecar.md`
