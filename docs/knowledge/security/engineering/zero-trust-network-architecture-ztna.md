# Zero Trust Network Architecture (ZTNA)

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your organization relies on a perimeter-based security model — a VPN
gives full network access once a user connects. Lateral movement after
credential compromise is easy because internal traffic is implicitly
trusted. Remote workers, contractors, and cloud workloads bypass the
perimeter entirely. You cannot enforce granular access to individual
applications or verify device posture before granting access.

## Context

Zero Trust Network Architecture (ZTNA) replaces the castle-and-moat
model with "never trust, always verify." Every access request — user,
device, or service — is authenticated, authorized, and continuously
validated regardless of network location. In 2026, ZTNA has evolved
from a remote access technology to a universal access model that
replaces all network-level access controls. Gartner identifies securing
machine identities (AI agents, service accounts, API keys, automation
scripts) as a top CISO priority, extending zero trust to non-human
actors. The NIST SP 800-207 Zero Trust Architecture standard provides
the federal baseline, referenced by FedRAMP, CMMC 2.0, and multiple
state-level cybersecurity frameworks.

## VPN vs. ZTNA

| Feature | Traditional VPN | ZTNA |
|---|---|---|
| Access scope | Full network access | Per-application access |
| Authentication | One-time at connect | Continuous verification |
| Device posture | Optional | Required |
| Lateral movement | Easy after compromise | Blocked by microsegmentation |
| Cloud support | Backhauled through DC | Direct-to-app |
| Performance | Hairpin through concentrator | Edge-optimized |
| Scalability | VPN concentrator bottleneck | Cloud-native, elastic |

## Core principles

```
1. Verify explicitly
   → Authenticate and authorize every access request
   → Use identity, device, location, behavior signals

2. Least privilege access
   → Grant minimum necessary permissions
   → Time-bound and just-in-time access

3. Assume breach
   → Microsegment the network
   → Encrypt all traffic (internal and external)
   → Monitor continuously for anomalies

4. Continuous validation
   → Re-evaluate trust on every request
   → Device posture checks (patch level, EDR, encryption)
   → Adaptive risk-based authentication
```

## Implementation layers

```
Layer 1: Identity (foundation)
  → Enterprise IdP (Azure AD, Okta, Ping)
  → MFA everywhere (phishing-resistant: passkeys, FIDO2)
  → Machine identity management (SPIFFE/SPIRE for workloads)

Layer 2: Device trust
  → Device posture assessment (OS version, disk encryption, EDR)
  → Managed vs. unmanaged device policies
  → Certificate-based device identity

Layer 3: Network microsegmentation
  → Per-application tunnels (not network tunnels)
  → Service mesh mTLS (Istio, Cilium)
  → Software-defined perimeter (SDP)

Layer 4: Application access
  → ZTNA broker as reverse proxy
  → Per-request authorization (not per-session)
  → Application-level WAF and threat inspection

Layer 5: Data protection
  → DLP policies at the access layer
  → Encryption at rest and in transit (TLS 1.3)
  → Classification-based access controls
```

## ZTNA deployment models

| Model | Description | Use case |
|---|---|---|
| **Agent-based** | Device agent establishes outbound tunnel | Managed devices, full posture check |
| **Service-initiated** | Connector in app network, no agent | BYOD, contractors, unmanaged devices |
| **Universal** | Combines both models | Hybrid workforce (2026 standard) |

## Platform comparison (2026)

| Feature | Cloudflare Access | Zscaler ZPA | Palo Alto Prisma | Tailscale |
|---|---|---|---|---|
| Type | Cloud-native ZTNA | Cloud ZTNA | SASE + ZTNA | Mesh VPN / ZTNA |
| Agent required | Optional | Yes | Yes | Yes (lightweight) |
| IdP integration | All major | All major | All major | All major |
| Device posture | WARP client | ZPA agent | GlobalProtect | ACL-based |
| Pricing model | Per user/mo | Per user/mo | Per user/mo | Free tier + per user |
| Self-hosted option | No | No | No | Yes (Headscale) |

## Anti-patterns

- **VPN + ZTNA hybrid without migration plan** — running both a VPN
  and ZTNA side-by-side indefinitely. Users bypass ZTNA by connecting
  to the VPN for "easier" access, undermining the zero trust model.
  Set a VPN sunset date and migrate application by application.
- **ZTNA without device posture** — authenticating users without
  verifying device health. A compromised device with valid credentials
  still exposes applications. Require device posture checks (EDR,
  encryption, OS version) for every access request.
- **Static trust decisions** — granting access based on a single
  authentication event. Trust must be continuously evaluated — device
  posture, user behavior, and risk signals change during a session.
- **Ignoring machine identities** — applying zero trust only to human
  users while service accounts, API keys, and CI/CD tokens have
  broad, static access. Extend zero trust to workload identities
  with SPIFFE/SPIRE or cloud IAM workload identity federation.

## Gotchas

- **Legacy application compatibility** — applications that rely on
  IP-based allowlisting or lack modern authentication (SAML, OIDC)
  require an application connector or reverse proxy that translates
  ZTNA identity to legacy auth mechanisms.
- **Performance overhead** — per-request authentication adds latency.
  Use session tokens with short TTLs (5-15 minutes) and cache
  authorization decisions at the edge to minimize impact.
- **Split-tunnel complexity** — deciding which traffic goes through
  the ZTNA broker and which goes direct. Default to routing all
  traffic through ZTNA; whitelist only verified-safe destinations.
- **Contractor and BYOD access** — agent-based ZTNA requires
  installing software on unmanaged devices, which contractors may
  resist. Use service-initiated (agentless) ZTNA for external users,
  with stricter DLP policies.

## Verification

- All application access routes through a ZTNA broker (no direct
  network access).
- MFA is enforced for every user and device.
- Device posture checks are mandatory for managed devices.
- Machine identities use short-lived, rotated credentials.
- Microsegmentation prevents lateral movement between services.
- VPN is decommissioned or on a documented sunset timeline.

## Related

- `documentation/docs/policies/security/oauth-jwt-session-patterns.md`
- `documentation/docs/policies/cloudflare/zero-trust-access-tunnel-warp.md`
- `documentation/docs/policies/compliance/soc2-type-ii-audit-preparation.md`

## Source URLs (verified 2026-08-16)

- ZTNA in 2026: How It Works — https://www.venn.com/learn/zero-trust/ztna/
- Zero Trust Security: 2026 Complete Guide — https://blog.jazzcybershield.com/zero-trust-network-security-guide-2026/
- Zero Trust Architecture: Complete Guide 2026 — https://www.startupdefense.io/blog/zero-trust-architecture-complete-guide-2026
- Zero Trust Security Implementation Guide — https://icanio.com/insights/zero-trust-security-implementation-enterprise-guide
