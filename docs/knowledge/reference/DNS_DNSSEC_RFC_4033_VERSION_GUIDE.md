---
title: "DNS Security Extensions (DNSSEC) Version Guide (RFC 4033, RFC 4034, RFC 4035)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 4033, RFC 4034, RFC 4035 and selected updates; https://www.rfc-editor.org/rfc/rfc4033"
---

# DNS Security Extensions (DNSSEC) Version Guide (RFC 4033, RFC 4034, RFC 4035)

## Scope

Reference card for DNS Security Extensions (DNSSEC) as defined in RFC 4033 (introduction and requirements), RFC 4034 (resource records for the security extensions), and RFC 4035 (protocol modifications). Used by network, security, and platform teams when documenting signed-zone operations, recursive resolver validation, and key-management policies.

## Identifier table

| Field | Value |
| --- | --- |
| Primary documents | RFC 4033, RFC 4034, RFC 4035 |
| Status | Standards Track, Proposed Standard |
| Obsoletes | RFC 2535, RFC 3008, RFC 3090, RFC 3445, RFC 3655, RFC 3658, RFC 3755, RFC 3845 |
| New resource records | DNSKEY, RRSIG, NSEC, DS, NSEC3 (RFC 5155), NSEC3PARAM, CDS, CDNSKEY, TLSA (RFC 6698) |
| Selected updates | RFC 5011 (trust anchor rollover), RFC 5155 (NSEC3), RFC 5702 (SHA-2), RFC 6605 (EDNS Chain Query), RFC 6781 (DNSSEC operational practices), RFC 6840 (DNSSEC clarifications), RFC 6975 (signing DNSSEC zone), RFC 7344 (CDS/CDNSKEY), RFC 8078 (DS automation), RFC 8198 (aggressive negative caching), RFC 8624 (algorithm implementation requirements), RFC 8749 (EdDSA), RFC 8945 (signer requirements), RFC 9076 (NSEC3 closest encloser proof), RFC 9156 (root zone rollover) |
| Verification source | https://www.rfc-editor.org/rfc/rfc4033 and successor RFCs |

## Plan

1. Identify the zone type (authoritative forward, authoritative reverse, recursive resolver).
2. Select the DNSSEC signing algorithm suite per RFC 8624.
3. Plan key lifecycle: KSK/ZSK generation, rollover per RFC 5011, and DS record publication to the parent.
4. Configure validation on recursive resolvers and verify with trusted anchors.
5. Document NSEC vs NSEC3 (RFC 5155) choice and proof-of-non-existence handling.

## Inputs

- Zone file or dynamic zone configuration.
- Key generation parameters (algorithm, key length, lifetime, roll schedule).
- Trust anchor configuration on recursive resolvers.
- Parent zone DS publication workflow (registry EPP, CDS/CDNSKEY automation).

## ORCHORDS Profile

This guide is used as a reference for DNSSEC documentation and operational design. It does NOT introduce protocol behavior beyond what RFCs specify. When an operational requirement exceeds what is captured here, escalate to a fresh RFC review and the IANA DNSSEC algorithm registry.

## Implementation Notes

- RFC 8624 defines mandatory-to-implement DNSSEC signing algorithms; deprecated algorithms (RSAMD5, DSA, SHA-1 in DNSSEC context) must not be used.
- NSEC3 (RFC 5155) is preferred over NSEC when zone-walking must be prevented.
- RFC 5011 trust anchor rollover allows recursive resolvers to roll the root trust anchor automatically.
- CDS / CDNSKEY records (RFC 7344) and DS automation (RFC 8078) support parent-child DNSSEC maintenance.
- Negative response trust (RFC 8198) and authenticated denial of existence (RFC 5155) must be considered together.

## Companion Documents

- RFC 8624 (algorithm implementation requirements)
- RFC 6781 (DNSSEC operational practices)
- RFC 9156 (root zone KSK rollover)
- IANA DNSSEC algorithm registry
