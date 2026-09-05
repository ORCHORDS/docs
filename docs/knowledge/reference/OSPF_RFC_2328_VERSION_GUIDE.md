---
title: "OSPF Version 2 Protocol Version Guide (RFC 2328)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 2328 and selected updates; https://www.rfc-editor.org/rfc/rfc2328"
---

# OSPF Version 2 Protocol Version Guide (RFC 2328)

## Scope

Reference card for Open Shortest Path First version 2 (OSPFv2) as specified in IETF RFC 2328, with selected updates including RFC 5709 (HMAC-SHA algorithm), RFC 7474 (router information LSA), RFC 8042 (OSPF Two-Part metric), RFC 8362 (OSPFv3 link-local signaling), and RFC 9355 (OSPF API). Used by network and operations teams when documenting intra-domain routing for IPv4 networks.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 2328, "OSPF Version 2" |
| Status | Internet Standard (STD 54) |
| Obsoletes | RFC 2178 |
| Algorithm | Dijkstra shortest path first |
| LSA types | Router (1), Network (2), Summary (3), Summary (4), AS-external (5), Group Membership (6), NSSA External (7), External Attributes (8), Opaque (9, 10, 11) |
| Network types | Broadcast, Point-to-Point, Point-to-Multipoint, NBMA, Virtual Link |
| Verification source | https://www.rfc-editor.org/rfc/rfc2328 and successor RFCs |

## Plan

1. Identify the deployment context (service provider core, enterprise campus, data center fabric, hybrid cloud interconnect).
2. Determine the area topology: backbone area (0.0.0.0) and attached non-backbone areas.
3. Define the authentication plan (MD5 deprecated; HMAC-SHA per RFC 5709 with explicit key rotation).
4. Capture convergence, summarization, and stub/NSSA design decisions.
5. Document the validation plan (LSA throttling, SPF throttling, neighbor change logging).

## Inputs

- Router ID allocation scheme.
- Area topology diagram and address plan.
- Interface cost, network type, and authentication configuration.
- Route redistribution policy between OSPF and other protocols (BGP, static, connected).

## ORCHORDS Profile

This guide is used as a reference for OSPF documentation and design reviews. It does NOT introduce protocol behavior beyond what RFCs specify. When an operational requirement exceeds what is captured here, escalate to a fresh RFC review and the IANA OSPF parameters registry.

## Implementation Notes

- RFC 2328 defines OSPFv2; authentication choices should default to HMAC-SHA per RFC 5709.
- MD5 authentication (RFC 2154) is deprecated; review and migrate to a stronger algorithm.
- Use stub, totally stubby, NSSA, or totally NSSA areas only when the area design justifies them.
- LSA and SPF throttling values must reflect the convergence SLO; do not copy default values without analysis.
- Route redistribution must be bidirectional and policy-controlled; use route tags and prefix-lists to prevent loops.

## Companion Documents

- RFC 5340 (OSPFv3 for IPv6)
- RFC 5709 (OSPFv2 HMAC-SHA authentication)
- RFC 7474 (Router Information LSA)
- RFC 8042 (Two-Part metric)
- RFC 8362 (OSPFv3 link-local signaling, informational)
- IANA OSPF parameters registry
