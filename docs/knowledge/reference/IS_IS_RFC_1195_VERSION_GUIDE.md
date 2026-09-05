---
title: "IS-IS for IP Networks Version Guide (RFC 1195, RFC 5308)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 1195 and RFC 5308; https://www.rfc-editor.org/rfc/rfc1195"
---

# IS-IS for IP Networks Version Guide (RFC 1195, RFC 5308)

## Scope

Reference card for Intermediate System to Intermediate System (IS-IS) routing protocol as extended for IP networks in RFC 1195 (dual IS-IS) and RFC 5308 (routing IPv6 with IS-IS). Used by network and operations teams documenting large-scale service provider or data center networks where IS-IS is the chosen IGP.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 1195, "Use of OSI IS-IS for Routing in TCP/IP and Dual Environments" |
| Status | Internet Standard (Proposed Standard originally; widely deployed) |
| ISO document | ISO 10589 |
| IPv6 extension | RFC 5308, "Routing IPv6 with IS-IS" |
| Selected updates | RFC 3277, RFC 3786, RFC 4444, RFC 4972, RFC 5301, RFC 5303, RFC 5304, RFC 5310, RFC 6165, RFC 6232, RFC 7356, RFC 7602, RFC 7794, RFC 8570, RFC 8919, RFC 9130, RFC 9472 |
| PDU types | LSP, CSNP, PSNP, Hello |
| TLV / sub-TLVs | Area ID, LSP Buffersize, IS Neighbors, IP Interface Address, IP Internal/External Reachability, Extended IP Reachability (RFC 5305), IPv6 Reachability (RFC 5308), Router Capability (RFC 7981) |
| Verification source | https://www.rfc-editor.org/rfc/rfc1195 and successor RFCs |

## Plan

1. Identify the deployment context (large service provider, transit network, data center spine-leaf).
2. Choose the addressing model: single-topology (RFC 1195) or multi-topology (RFC 5120).
3. Plan NET (Network Entity Title) allocation and area boundaries.
4. Define authentication (RFC 5304 / RFC 5310 for HMAC; update via current best-practice RFCs).
5. Capture convergence tuning (LSP generation, SPF, PRC throttles) and wide-metric values.
6. Document IPv6 reachability strategy: where IPv6 is required, use RFC 5308 reachability TLVs.

## Inputs

- IS-IS NET plan (NSAP format with area ID and system ID).
- Topology and area design (single area or multi-area with L2/L1 boundaries).
- Interface and wide-metric plan.
- Authentication material and rotation policy.
- Adjacency scope (L1 only, L2 only, or L1L2).

## ORCHORDS Profile

This guide is used as a reference for IS-IS documentation and design reviews. It does NOT introduce protocol behavior beyond what RFCs specify. When an operational requirement exceeds what is captured here, escalate to a fresh RFC review and the IANA IS-IS parameters registry.

## Implementation Notes

- RFC 1195 extends ISO 10589 IS-IS to carry IPv4 reachability; IPv6 requires RFC 5308 (or RFC 5120 multi-topology).
- Wide metrics (RFC 3784, later RFCs) are recommended over narrow metrics.
- Authentication (RFC 5304 / RFC 5310) should be configured on all adjacencies; use rotating keys.
- Micro-loops can be reduced with RFC 6976 / RFC 8500 mechanisms where supported.
- Multi-instance IS-IS (RFC 6822 / RFC 9513) permits parallel IS-IS instances in the same data plane for separation.

## Companion Documents

- RFC 5120 (Multi-topology IS-IS)
- RFC 6822 (Multi-instance IS-IS, updated by RFC 9513)
- RFC 7981 (Router Capability TLV)
- IANA IS-IS TLV / sub-TLV registry
