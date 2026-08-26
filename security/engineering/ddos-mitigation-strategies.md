# DDoS Mitigation Strategies

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your service becomes unresponsive under a flood of traffic. Legitimate users
cannot access the application. Your origin servers are overwhelmed, your
bandwidth is saturated, or your application layer is exhausted by expensive
requests. You need a defense architecture that handles volumetric (L3/L4)
and application-layer (L7) DDoS attacks.

## Context

DDoS attacks target three layers: L3 (network — IP floods, amplification),
L4 (transport — SYN floods, UDP floods), and L7 (application — HTTP floods,
slowloris, API abuse). Effective mitigation requires defenses at each layer
because a single control cannot address all attack types. The 2026 landscape
is dominated by edge/cloud scrubbing services (Cloudflare, AWS Shield,
Fastly, Akamai) that absorb volumetric attacks at the network edge, combined
with application-layer controls for sophisticated L7 attacks.

## Layer-specific defenses

### L3/L4 (Network/Transport)

| Attack type | Defense | Implementation |
|---|---|---|
| Volumetric floods (UDP, ICMP) | Anycast scrubbing | Route traffic through an anycast network (Cloudflare, AWS Shield Advanced) that absorbs floods across 300+ PoPs |
| SYN floods | SYN cookies / SYN proxy | Enable at the edge or OS level (`net.ipv4.tcp_syncookies=1`) |
| Amplification (DNS, NTP, memcached) | BCP38 / source validation | Block spoofed source IPs at the network edge; filter UDP reflection vectors |
| Protocol abuse | ACL / firewall rules | Block unused protocols and ports at the network firewall |

### L7 (Application)

| Attack type | Defense | Implementation |
|---|---|---|
| HTTP floods | Rate limiting per endpoint | Scope by IP + endpoint + method; behavioral thresholds, not static |
| Slowloris / slow POST | Connection timeouts | Set aggressive `keepalive_timeout`, `client_body_timeout` in NGINX/CDN |
| API abuse | Authentication + rate limiting | Require API keys; rate limit per key, not just per IP |
| Credential stuffing | Bot management + CAPTCHA | Cloudflare Bot Management, AWS WAF Bot Control, Turnstile |
| Resource exhaustion | Request budgets | Limit request body size, query complexity (GraphQL depth), search parameters |

## Architecture pattern: edge-first defense

```
Client → Anycast Edge (Cloudflare/AWS CloudFront)
            ↓ L3/L4 scrubbing (volumetric absorbed here)
            ↓ L7 WAF (SQLi, XSS, bot detection)
            ↓ Rate limiting (per IP, per endpoint)
            ↓ Challenge page (CAPTCHA for suspicious traffic)
         Origin Server (only clean traffic reaches here)
```

## Rate limiting best practices

- **Scope tightly** — rate limit per IP + endpoint, not globally. A global
  limit lets an attacker consume the entire budget.
- **Behavioral thresholds** — 100 req/min to `/api/search` is normal for
  humans, suspicious for bots. Set per-endpoint thresholds based on
  legitimate traffic patterns.
- **Multi-layer rate limits** — combine edge rate limits (Cloudflare,
  CloudFront) with application-level limits (middleware) for defense in
  depth.
- **Return 429 with Retry-After** — tell legitimate clients when to retry.
  Attackers ignore this; legitimate clients respect it.

## Anti-patterns

- **Origin-only defense** — if DDoS traffic reaches your origin, you have
  already lost. Absorb volumetric attacks at the edge, not at the origin.
- **Static IP allowlists** — attackers rotate IPs. IP-based blocking alone
  is insufficient for L7 attacks.
- **Blocking entire countries** — geo-blocking creates false positives for
  legitimate users behind VPNs and shared IPs.
- **No distinction between attack types** — a volumetric SYN flood and an
  L7 HTTP flood require completely different defenses. Diagnose first.
- **Over-relying on CAPTCHA** — CAPTCHAs degrade UX and are increasingly
  solvable by bots. Use them as a challenge escalation, not the primary
  defense.

## Gotchas

- **Anycast ≠ DDoS protection** — anycast distributes traffic but does not
  filter it. You need scrubbing + anycast, not just anycast.
- **Origin IP exposure** — if your origin IP is known, attackers bypass the
  CDN. Never expose origin IPs in DNS, email headers, or API responses.
  Use Cloudflare Tunnels or AWS PrivateLink to hide the origin.
- **TLS handshake floods** — encrypted traffic is expensive to process. TLS
  handshake floods can exhaust your edge's TLS termination capacity. Ensure
  your CDN/edge handles TLS offloading at scale.
- **DNS as a single point of failure** — if your DNS provider goes down,
  your entire service is unreachable regardless of DDoS protection. Use
  multiple DNS providers.
- **Cost of L7 scrubbing** — L7 inspection at the edge is computationally
  expensive. AWS Shield Advanced costs $3,000/month. Budget accordingly.

## Verification

- **DDoS simulation** — use authorized load testing tools (Gremlin, red-
  button.net) to simulate attacks against your staging environment.
- **Origin isolation** — verify that your origin is unreachable without going
  through the CDN/edge layer.
- **Rate limit testing** — send requests above your configured thresholds
  and verify 429 responses.
- **Failover testing** — simulate edge provider failure and verify traffic
  shifts to backup (if multi-CDN).
- **Alert verification** — confirm that DDoS alerts fire within minutes of
  attack onset.

## Related

- `documentation/categories/security/waf-rules-configuration.md`
- `documentation/categories/security/rate-limiting-strategies.md`
- `documentation/categories/security/http2-rapid-reset-continuation-flood.md`
- `documentation/categories/cloudflare/big-three-gotchas.md`
- `documentation/categories/performance/api-response-caching.md`

## Source URLs (verified 2026-08-16)

- DDoS protection and mitigation 2026 guide — https://www.kentik.com/kentipedia/ddos-protection/
- DDoS attack prevention: 15 best practices 2026 — https://www.indusface.com/blog/best-practices-to-prevent-ddos-attacks/
- Best DDoS mitigation providers 2025-2026 — https://www.fastly.com/blog/best-ddos-mitigation-providers-2025-2026
- Cloudflare DDoS protection L3 L4 L7 guide — https://tasrieit.com/blog/cloudflare-ddos-protection-l3-l4-l7-guide
- How to prevent DDoS attacks — https://www.cloudflare.com/learning/ddos/how-to-prevent-ddos-attacks/
- Rate limiting best practices in DDoS mitigation — https://www.red-button.net/rate-limit-configuration-ddos-mitigation/
