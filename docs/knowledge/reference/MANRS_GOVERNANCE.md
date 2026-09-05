---
title: MANRS (Mutually Agreed Norms for Routing Security) Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: MANRS document set (https://www.manrs.org/), MANRS Network Operator / CDN&Cloud / Equipment Vendor / IXP programmes; https://www.manrs.org/about/
---

# MANRS (Mutually Agreed Norms for Routing Security) Governance

## Scope

This card governs how `orchords-docs` evaluates adherence to MANRS — the global initiative that defines operational norms for routing security. It is the reference input for any Internet-edge reference architecture that participates in inter-domain routing.

## Why this card exists

MANRS is the operational complement to the RPKI and BGPsec standards. It defines four action programmes for network operators, CDN/cloud providers, equipment vendors, and IXPs. Without an explicit card, the KB cites routing-security practices that do not survive MANRS conformance expectations.

## The four programmes

### Network Operators

The MANRS Network Operator programme requires:

| Action | Description |
|---|---|
| 1 — Filtering | prevent propagation of incorrect routing information (anti-spoofing, prefix filtering) |
| 2 — Anti-spoofing | prevent traffic with spoofed source IP from leaving the network |
| 3 — Coordination | facilitate communication between operators (NOC-to-NOC contacts, peeringDB) |
| 4 — Global validation | support RPKI ROA publication and enable ROV |

References: `https://www.manrs.org/netops/`.

### CDN and Cloud Providers

| Action | Description |
|---|---|
| 1 — Filtering | prevent propagation of incorrect routing information |
| 2 — Anti-spoofing | prevent traffic with spoofed source IP from leaving the network |
| 3 — Coordination | facilitate communication with peers / customers |
| 4 — Global validation | support RPKI ROA publication and enable ROV |
| 5 — DDoS mitigation | provide DDoS mitigation services to customers |
| 6 — Routing security | support RPKI, BGPsec, IRR |
| 7 — Customer support | provide routing-security support to customers |

References: `https://www.manrs.org/cdns/`.

### Equipment Vendors

| Action | Description |
|---|---|
| 1 — Design | design products that support MANRS actions |
| 2 — Implementation | implement the actions in products |
| 3 — Testing | test the actions in lab and customer environments |
| 4 — Documentation | publish documentation for the actions |

References: `https://www.manrs.org/vendors/`.

### IXPs (Internet Exchange Points)

| Action | Description |
|---|---|
| 1 — Filtering | prevent propagation of incorrect routing information |
| 2 — Anti-spoofing | prevent traffic with spoofed source IP from leaving the network |
| 3 — Coordination | facilitate communication between members |
| 4 — Global validation | support RPKI ROA publication and enable ROV |

References: `https://www.manrs.org/ixps/`.

## Implementation guidance

### Action 1 — Filtering

- Deploy prefix filtering on every eBGP session.
- Use IRR-based filters (RIPE IRR, RADB, NTTCOM).
- Use RPKI ROV filters.
- Reject bogons (RFC 6442) and martians.
- Apply max-prefix limits per session.

### Action 2 — Anti-spoofing

- Deploy BCP 38 / RFC 2827 ingress filtering.
- Deploy uRPF (unicast Reverse Path Forwarding) where applicable.
- Deploy BCP 84 / RFC 3704 at the network edge.
- Deploy SAV (Source Address Validation) per RFC 8704.

References: RFC 2827 (BCP 38), RFC 3704 (BCP 84), RFC 8704 (BCP 84 update).

### Action 3 — Coordination

- Publish NOC contacts on PeeringDB.
- Maintain a public abuse@ contact.
- Maintain a public peering@ contact.
- Use IRR (RPSL, RPKI) to publish routing policy.
- Participate in NANOG / RIPE / APNIC / ARIN meetings.

### Action 4 — Global validation

- Publish ROAs for all originated prefixes.
- Enable ROV on every eBGP session.
- Maintain a RPKI to Router session with a current validator cache.
- Optionally: participate in BGPsec deployment (RFC 8205).

## Mandatory pre-flight (before adopting a new network operator / CDN reference card)

1. NOC contact is published on PeeringDB.
2. ROAs are published for every originated prefix.
3. ROV is enabled on every eBGP session.
4. Prefix filters are configured per session.
5. Anti-spoofing is configured per session.
6. Anti-DDoS is documented.

## MANRS+ readiness

MANRS+ is a higher bar. The KB does not enforce MANRS+; it documents it for high-security reference architectures.

References: `https://www.manrs.org/manrs-plus/`.

## Sources

- MANRS home: `https://www.manrs.org/`
- MANRS Network Operator actions: `https://www.manrs.org/netops/`
- MANRS CDN & Cloud actions: `https://www.manrs.org/cdns/`
- MANRS Equipment Vendor actions: `https://www.manrs.org/vendors/`
- MANRS IXP actions: `https://www.manrs.org/ixps/`
- RFC 2827 (BCP 38): `https://www.rfc-editor.org/rfc/rfc2827`
- RFC 3704 (BCP 84): `https://www.rfc-editor.org/rfc/rfc3704`
- RFC 8704 (BCP 84 update): `https://www.rfc-editor.org/rfc/rfc8704`
- RFC 6442 (Bogon list): `https://www.rfc-editor.org/rfc/rfc6442`
