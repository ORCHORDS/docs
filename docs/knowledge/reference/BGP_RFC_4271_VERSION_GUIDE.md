---
title: "BGP-4 Protocol Version Guide (RFC 4271)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 4271 (and errata); https://www.rfc-editor.org/rfc/rfc4271"
---

# BGP-4 Protocol Version Guide (RFC 4271)

## Scope

Reference card for Border Gateway Protocol version 4 (BGP-4) as specified in IETF RFC 4271 and successor updates. Used by network, platform, and operations teams when documenting inter-domain routing decisions, peer policies, or BGPsec/Route Origin Authorization (RPKI) interactions. Treats RFC 4271 as the baseline protocol and RFCs 6793, 7606, 7607, 7705, 8210, 9234, 9494, and 9774 as selected updates.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 4271, "A Border Gateway Protocol 4 (BGP-4)" |
| Status | Internet Standard (STD 68) |
| Obsoletes | RFC 1771 |
| Updated by (selected) | RFC 6793, RFC 7606, RFC 7607, RFC 7705, RFC 8210, RFC 9234, RFC 9494, RFC 9774 |
| Path attributes | ORIGIN, AS_PATH, NEXT_HOP, MED, LOCAL_PREF, ATOMIC_AGGREGATE, AGGREGATOR, COMMUNITY, MP_REACH_NLRI, LARGE_COMMUNITY, BGP_LS, etc. |
| Finite State Machine | Idle, Connect, Active, OpenSent, OpenConfirm, Established |
| Notification codes | Message Header Error (1), OPEN Message Error (2), UPDATE Message Error (3), Hold Timer Expired (4), Finite State Machine Error (5), Cease (6) |
| Verification source | https://www.rfc-editor.org/rfc/rfc4271 and successor RFCs |

## Plan

1. Identify the deployment context (transit provider, edge network, IX route server, IXP, enterprise edge).
2. Map required features against RFC 4271 and the relevant updates (e.g., RFC 8210 for ADD-PATH, RFC 9234 for Route Leak Prevention, RFC 9494 for BGP Long-Lived Graceful Restart).
3. Capture the operational requirements: peer authentication (RFC 8205 / TCP AO via RFC 5925), RPKI origin validation (RFC 6480, RFC 6810, RFC 9319), and routing policy language.
4. Validate against the live registry (IANA BGP parameters) and operator policy documents.

## Inputs

- BGP session configuration (local AS, remote AS, peer IP, MD5 or TCP AO key, hold time, keepalive).
- Address families enabled (IPv4 unicast, IPv6 unicast, IPv4 VPN, EVPN, Flowspec).
- Route filtering policy (prefix-lists, AS-path filters, RPKI invalid reject policy, max-prefix).
- Operational policy (IRRDB registration, ROA presence, peeringDB record).

## ORCHORDS Profile

This guide is used as a reference when reviewing BGP documentation or designing peer templates. It does NOT introduce protocol behavior beyond what RFCs and IANA registry pages specify. When a network operation requires a behavioral rule that is not captured here, escalate to a fresh review against the current RFC and the IANA Border Gateway Protocol (BGP) parameters registry.

## Implementation Notes

- RFC 4271 defines the protocol; implementation choices (4-byte ASN per RFC 6793, ADD-PATH per RFC 8210, BGPsec per RFC 8205, RPKI origin validation per RFC 6810) are configuration decisions.
- Use RPKI ROAs and route filtering together; do not rely on RPKI alone.
- Graceful restart (RFC 4724, updated by RFC 9494) requires Long-Lived Graceful Restart capability negotiation where applicable.
- Route leak prevention (RFC 9234) provides a community-based signaling mechanism for leak detection; pair with operator policy and IRRDB registrations.
- For Internet exchange points, consult the IXP route server implementation documents and the peeringDB record.

## Companion Documents

- RFC 6480 (RPKI architecture)
- RFC 6810 (RPKI to Router)
- RFC 8205 (BGPsec)
- RFC 9319 (RPKI operational practices)
- IANA Border Gateway Protocol (BGP) parameters registry
