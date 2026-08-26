# magic-transit-spectrum-network-edge

**Issue:** Traffic is arriving at the origin over protocols and paths the normal orange-cloud proxy + WAF stack cannot touch: the company advertises its own IP prefixes out of a datacenter (raw TCP/UDP, no HTTP), partners need SSH/RDP exposed to the internet without publishing the origin IP, and volumetric L3 floods target the IP space directly rather than any hostname. The team needs to know when Magic Transit (BGP/GRE or CNI absorption of your prefixes), Cloudflare Network Firewall (formerly Magic Firewall, network-layer policy), or Spectrum (proxying arbitrary TCP/UDP) is actually required — versus staying on plain proxy + WAF — and what each one costs in plan tier and operational complexity.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When plain proxy + WAF is not enough

1. **What the standard stack already covers.** Proxied (orange-cloud) HTTP(S) hostnames get unmetered L3/4 and L7 DDoS mitigation, WAF, bot, and rate-limiting features automatically on every plan — for hostname-based HTTP traffic this is almost always sufficient, and Under Attack Mode handles L7 emergencies (`under-attack-mode-ddos-runbook.md`).
2. **Gap 1 — your own IP prefixes.** The proxy model protects *hostnames in Cloudflare zones*. If you advertise your own IP space (on-prem routers, gaming servers, VoIP, anything with no DNS hostname in front), volumetric attacks hit your routers directly. That gap is Magic Transit's job.
3. **Gap 2 — non-HTTP protocols.** SSH, RDP, Minecraft, custom TCP/UDP game/API protocols are not proxyable by the HTTP pipeline; grey-clouding them exposes origin IPs and forfeits all edge protection. That gap is Spectrum's job (or Cloudflare Tunnel when the origin can dial out).
4. **Gap 3 — network-layer policy.** WAF rules match HTTP requests. Filtering by IP/port/protocol across an entire network (all protocols, all prefixes) needs a network firewall, not a web application firewall.

## Magic Transit (Enterprise): BGP in, tunnels back

1. **What it is.** An Enterprise-only product where Cloudflare announces your IP prefixes via BGP, making its network "the front door to your IP network": traffic lands on Cloudflare anycast across hundreds of cities, gets DDoS-filtered and optionally accelerated, then is forwarded to your infrastructure. It covers on-premises, cloud-hosted, and hybrid networks.
2. **Getting traffic back to you.** Clean traffic returns over anycast GRE tunnels across the public internet, or over Cloudflare Network Interconnect (CNI) — a physical or virtual interconnect that avoids the public internet entirely. GRE is stateless and unencrypted; IPsec tunnels add encryption and authentication.
3. **Egress is not automatic.** By default, return traffic egresses via your ISP interface, not Cloudflare. For ingress+egress (Cloudflare as the full path), implement policy-based routing (PBR) or default-route traffic into the tunnels; Direct Server Return is the documented egress pattern.
4. **Tunnel mechanics.** Endpoints pair a Cloudflare address with your router address; any server in any Cloudflare data center can receive traffic for a tunnel (anycast GRE). With a standard 1500-byte internet MTU, adjust MSS to account for encapsulation headers or you get silent PMTU black holes. IPsec requires IKEv2 with PSK, supports NAT-T (4500), recommends route-based VPNs, Child SA rekey between 30 minutes and 8 hours, and a post-quantum hybrid key exchange (ML-KEM-768 + DH Group 20) is the current recommendation.
5. **Prefix requirements and helpers.** Networks must meet the `/24` minimum prefix-length expectation for advertisement; if yours cannot, Cloudflare can front you with Cloudflare-owned IP addresses. A BGP peering beta can automate adding/removing networks. Health checks run per tunnel with configurable frequency and health alerts; Magic Transit's China Network support is not available.
6. **On-demand Magic Transit.** A pay-as-you-go posture: prefixes stay unadvertised normally and you switch on advertisement (dashboard or API) during an attack. It requires BYOIP prefixes — it cannot be combined with Cloudflare-leased IPs — and dynamic advertisement does not work with BGP-controlled advertisement, so pick the on-demand method at prefix onboarding, not during the incident.

## Cloudflare Network Firewall (formerly Magic Firewall)

1. **What it is.** A firewall-as-a-service running on Cloudflare's global network, filtering your traffic *before it reaches your network* — network-layer allow/deny rules on criteria like protocol and packet length, written in the Cloudflare Rules language (Wireshark-inspired syntax). It is the L3/4 counterpart to the HTTP WAF, not a replacement for it.
2. **Availability.** Enterprise-only, included with the purchase of Magic Transit or Cloudflare WAN (the product formerly known as Magic WAN). If you see "Magic Firewall" in older runbooks or dashboards, it is this product renamed.
3. **Extras.** IDS monitors known threat signatures (ransomware, exfiltration styles) on your flows; packet captures can be taken from the dashboard for rule debugging — both documented under the Cloudflare Network Firewall docs tree.
4. **Design note.** Default posture should be "allow established, allow your documented protocols, deny the rest" applied to all ingress on the tunneled prefixes; pair with Magic Transit analytics (network analytics, bandwidth queries, tunnel health) for verification, the same log-then-enforce discipline the HTTP WAF uses.

## Spectrum: proxying arbitrary TCP/UDP

1. **What it is.** A global TCP/UDP proxy on Cloudflare edge nodes. It terminates the TCP/UDP sockets in both directions at Layer 4 and passes L4 payloads through unmodified — it does not inspect or modify application-layer protocols, cannot convert HTTP↔HTTPS, add headers, or apply WAF rules to raw TCP. For CDN/Workers/Bot Management on a Spectrum app, set its application type to HTTP/HTTPS so traffic rides the full pipeline.
2. **Plan availability (verified 2026-08).** Spectrum is a paid add-on on Pro and Business, included-capacity on Enterprise. Arbitrary TCP, UDP, HTTP, and HTTPS apps are Enterprise-only. Pro gets exactly one SSH app and one Minecraft app; Business adds exactly one RDP app. Do not promise "Spectrum for our TCP protocol" below Enterprise.
3. **Origins.** An app can point at a direct IP address, a CNAME/DNS origin, a load balancer, or a Tunnel virtual-network origin (private IPs routable through a connector — single IP only: no port ranges, no `origin_dns`, no multiple `origin_direct` addresses, and `proxy_protocol` must be off for vnet origins).
4. **Why use it.** It hides the origin IP for TCP services, gives L3/4 DDoS protection and anycast latency for non-HTTP protocols, and supports Proxy Protocol to preserve client IPs on direct-IP origins. Event logs and L7 (HTTP-type) analytics are available for verification.

## Choosing between them

1. **HTTP(S) website or API** → orange-cloud proxy + WAF (+ Bot Management where bought). None of these three products is needed.
2. **SSH/RDP/Minecraft for a small team** → Spectrum (Pro: SSH/Minecraft one app each; Business adds RDP). For pure admin access with no inbound ports at all, prefer Cloudflare Tunnel + Access instead — outbound-only beats a proxied listener.
3. **Custom TCP/UDP protocol for customers (game servers, MQTT, database front-ends) with hidden origins** → Spectrum, which means Enterprise for full protocol freedom.
4. **Your own IP prefixes / datacenter network under L3 flood** → Magic Transit (+ CNI instead of GRE if you want private interconnect), with Cloudflare Network Firewall rules as the network policy layer. This is the only option that protects IP space itself rather than hostnames or listeners.
5. **Both web and non-web on the same prefixes** → Magic Transit for the network layer, normal proxy + WAF for the HTTP hostnames inside it; the two are complementary, not competing.

## Related

- `under-attack-mode-ddos-runbook.md` — the L7 emergency procedure that stays relevant on top of any of these network-layer products.
- `paid-tier-security-upgrade-runbook.md` — plan-tier sequencing for these Enterprise purchases (written in parallel with this article).
- `free-tier-domain-security-runbook.md` — the baseline DDoS/proxy posture that suffices before any of these gaps apply.
- `zero-trust-access.md` — Tunnel + Access as the no-inbound-ports alternative to Spectrum for admin surfaces.
- `waf-best-practices.md` — the HTTP-side policy layer these products deliberately do not replace.
