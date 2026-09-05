---
title: BGP v4 Version Governance (RFC 4271, RFC 6286, RFC 8205, RFC 9234)
owner: ORCHORDS Platform Architecture
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: "IETF RFC 4271 (January 2006); RFC 6286 (June 2011); RFC 8205 (September 2017); RFC 9234 (May 2022); https://www.rfc-editor.org/rfc/rfc4271"
---

# BGP v4 Version Governance

## Scope

This card governs how ORCHORDS designs, operates, and audits deployments that
carry Border Gateway Protocol version 4 (BGP-4) sessions on the network edge,
between routing domains, or within a service provider interconnect. It binds the
canonical protocol specification (RFC 4271), the Autonomous System Number (ASN)
transition guidance (RFC 6286), Route Origin Authorisation / Route Origin
Validation (RPKI ROA / ROV, RFC 8205), and the BGP Long-Lived Graceful Restart
mechanism (RFC 9234) to a single reviewable artefact.

## Why BGP-4 matters here

BGP-4 is the inter-domain routing protocol that ties the internet — and any
multi-region cloud network — together. A BGP misconfiguration is one of the
most common causes of large-scale traffic black-holing, route leaks (RFC 7908
defines an incident taxonomy), and accidental prefix hijacks. Even when
ORCHORDS operates its own Autonomous System (AS) for outbound reachability,
every transit provider, internet exchange, and cloud peering edge terminates a
BGP-4 session, and the operational discipline applied to those sessions is what
keeps ORCHORDS assets reachable and trusted.

## Protocol identity

| Field | Value |
| --- | --- |
| Protocol | Border Gateway Protocol version 4 (BGP-4) |
| Transport | TCP, port 179, TTL 1 on external peering |
| Wire encoding | TLV-style UPDATE, NOTIFICATION, KEEPALIVE, OPEN, ROUTE-REFRESH (RFC 2918) |
| Path attributes | ORIGIN, AS_PATH, NEXT_HOP, MED, LOCAL_PREF, COMMUNITIES (RFC 1997), EXTENDED_COMMUNITIES (RFC 4360), LARGE_COMMUNITIES (RFC 8092), MP_REACH_NLRI (RFC 4760) |
| Finite State Machine | Idle, Connect, Active, OpenSent, OpenConfirm, Established |
| Hold time | Negotiated; recommended 90 s eBGP, 180 s iBGP |
| Keepalive | 1/3 of hold time |
| Message size | 4096 bytes minimum, 65535 maximum |
| ASN space | 32-bit (RFC 6793), 16-bit still widely carried |

## Capability advertisement (RFC 5492)

BGP speakers MUST advertise Multiprotocol Extensions, Route Refresh, and
support for 32-bit ASNs before relying on them. The OPEN message carries an
optional parameters block; a peer that rejects a required capability sends
NOTIFICATION and the session drops back to Idle.

## Path selection summary

Decision process when multiple eligible routes exist:

1. Highest WEIGHT (Cisco proprietary, locally significant).
2. Highest LOCAL_PREF (propagated within an AS).
3. Locally originated routes.
4. Shortest AS_PATH length.
5. Lowest ORIGIN (IGP < EGP < incomplete).
6. Lowest MED, compared only between paths from the same neighbouring AS.
7. eBGP over iBGP.
8. Lowest IGP cost to NEXT_HOP.
9. Oldest route (stability).
10. Lowest router ID (tie-break).

Operators must be able to reason about every step for every active prefix,
which is why reproducible BGP state capture (see Playbook below) is a
required control.

## RPKI and ROA / ROV (RFC 8205, RFC 8210)

Route Origin Authorisations are cryptographically signed objects that bind
an AS number to an IP prefix and a maximum prefix length. Route Origin
Validation rejects UPDATE messages that violate an enabled ROA:

- `valid` — origin AS and prefix length match an enabled ROA.
- `invalid` — prefix is covered by a ROA but origin AS or prefix length
  mismatch; MUST be rejected by default.
- `not-found` — prefix has no covering ROA; operator policy decides.

ORCHORDS policy: every edge router MUST run RPKI-RTR (RFC 8210) with a
trusted anchor store; `invalid` routes are dropped; `not-found` routes are
accepted but tagged with an RPKI community for observability.

## Long-Lived Graceful Restart (RFC 9234)

LLGR extends Graceful Restart (RFC 4724) so that stale routes may be retained
for hours instead of seconds during a control-plane restart of a peer. LLGR
must only be relied on when the documented stale-time is bounded, and the
local forwarding plane must mark LLGR-stale routes with a distinct community
so they can be filtered at the edge.

## GTSM and TTL security (RFC 5082)

The Generalized TTL Security Mechanism forces BGP packets to be sent with
TTL 255 and rejected if received with TTL less than 254. This blocks
off-path attackers from injecting forged packets. ORCHORDS requires GTSM on
all single-hop eBGP sessions.

## Operations and safety controls

- **MD5 / TCP-AO authentication.** iBGP sessions MUST use TCP-AO (RFC 5925)
  with key rotation every 180 days. eBGP sessions over dedicated interconnects
  SHOULD use TCP-AO where both peers support it; otherwise MD5 (RFC 2385) is
  the legacy minimum.
- **Prefix filtering.** Apply ingress and egress prefix filters (RFC 7454)
  with IRR-derived sets, deny `0.0.0.0/0` and the bogon list (RFC 6890), and
  enforce a hard prefix-length ceiling.
- **Max-prefix.** Each peer MUST have a max-prefix limit with an alarm at 80 %
  and a session reset at 100 %.
- **Route flap damping.** Disabled globally — RFC 7196 deprecates RFD for
  global Internet routes. Selective damping MAY be used for internal iBGP
  when justified by an incident review.
- **Configuration as code.** Every BGP configuration is rendered from a
  versioned source-of-truth; manual edits on routers are prohibited.
- **Pre/post snapshot.** A `show bgp ipv4 unicast` and `show bgp ipv6 unicast`
  capture is required before and after every peering change.

## Deprecations and superseded work

- BGP-1 / BGP-2 / BGP-3 — historical, MUST NOT be used.
- RFD for global BGP — deprecated by RFC 7196.
- 16-bit ASN assumption — superseded by RFC 6793; planners MUST reserve a
  32-bit capable ASN.
- ROA-vs-ROV confusion — RFC 8210 is the wire protocol for ROV; ROA alone
  does nothing without a relying party.

## Reviewer checklist

- [ ] All eBGP peers have GTSM, prefix-limit, and ROA enforcement.
- [ ] iBGP sessions use TCP-AO with key rotation evidence.
- [ ] Routing changes run through change management with a pre/post snapshot.
- [ ] RPKI validator health (cache age, expired ROAs) is monitored.
- [ ] AS_PATH and community strategies are documented per peer.
- [ ] No deprecated BGP features (RFD, ROA-only, MD5-only on iBGP).

## Source of truth

RFC 4271 is the canonical protocol definition; RFC 6286 covers the
four-byte ASN transition; RFC 8205 codifies ROV; RFC 9234 codifies LLGR.
Operational practice draws on RFC 7454 (BGP route filtering), RFC 7908
(incident taxonomy), RFC 5082 (GTSM), and RFC 8210 (RPKI-RTR).
