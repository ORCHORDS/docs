---
title: "RFC 4033 DNSSEC Introduction"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 4033 (March 2005); https://www.rfc-editor.org/rfc/rfc4033"
---

# RFC 4033 DNSSEC Introduction

## Scope

Reference card for IETF RFC 4033, *DNS Security Introduction and Requirements* (March 2005). RFC 4033 is the introductory companion to RFCs 4034 (resource records) and 4035 (protocol modifications) which together introduced DNSSECbis to the IETF. Profiles governing DNSSEC validation, signing, or operational policy should reference RFC 4033 for requirements and bind to RFCs 4034, 4035, and the operational extensions (RFC 6781, RFC 6841, RFC 7583, RFC 8078, RFC 9615) for protocol details.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 4033 (March 2005) |
| Status | Proposed Standard |
| Companion protocol | RFC 4034 (resource records), RFC 4035 (protocol modifications) |
| Companion operational | RFC 6781, RFC 6841, RFC 7583, RFC 8078, RFC 9615 |
| Companion measurement | RFC 8460 (SMTP TLS Reporting), RFC 8461 (MTA-STS), RFC 8462 (SMTP TLSRPT) |
| Source URL | https://www.rfc-editor.org/rfc/rfc4033 |

## Plan

1. Reference RFC 4033 by revision whenever a profile governs DNSSEC requirements; bind to RFC 4034 and RFC 4035 for protocol details.
2. Specify the DNSSEC deployment model in use: validating resolver (security-aware recursive resolver that performs validation for downstream clients) versus signing authoritative zone (the zone operator side).
3. Specify the chain-of-trust model: trust anchors, secure entry points, delegations, and DS records at zone cuts.
4. Specify the signature validity period, key rollover procedure, and the operational procedure for handling signature expiration.
5. Specify the negative response authentication policy (NSEC, NSEC3, NSEC5) and the trade-off with zone enumeration.
6. Specify the response policy when DNSSEC validation fails (SERVFAIL versus resolution with bogus data). Modern resolvers default to SERVFAIL, which is the safer choice.

## Inputs

- RFC 4033 requirements section; RFC 4034 resource record formats; RFC 4035 protocol modifications.
- Operational guidance from RFC 6781 (DNSSEC operational practices) and RFC 7583 (DS digest algorithms).
- Internal zone inventory: signed zones, trust anchors, and the chain-of-trust configuration.
- Resolver configuration: trust anchors, validation policy, fallback policy.

## ORCHORDS Profile

ORCHORDS treats RFC 4033 as the canonical introduction to DNSSEC requirements. Profiles that reference DNSSEC should bind to RFCs 4033, 4034, and 4035 as a unit and identify the role (signing authoritative zone, validating resolver, or both). A profile that references DNSSEC without binding to the three-part normative stack is non-conformant.

Profiles that govern SMTP MTA-STS or SMTP TLS Reporting (RFC 8460, RFC 8461) should reference RFC 4033 only when DNSSEC is used as a trust anchor for the MTA-STS policy; MTA-STS does not require DNSSEC.

## Implementation Notes

- DNSSEC adds authentication to DNS but not confidentiality; do not assume DNSSEC protects query content.
- NSEC3 provides zone-enumeration resistance at the cost of extra work; modern deployments should prefer NSEC3 with opt-out for large delegations.
- CDS / CDNSKEY (RFC 8078) and CSYNC (RFC 9615) support automated DS management between parent and child.
- Algorithm rollover (RFC 6781 §4) must be planned; an unplanned algorithm deprecation can cause widespread validation failures.
- The signed response must be revalidated when a zone key is rolled; treat the rollover as an operational event with explicit milestones.

## Companion Documents

- [NIST SP 800-81 Secure DNS](NIST_SP_800_81_SECURE_DNS.md)
- [RFC 8460 SMTP TLS Reporting](RFC_8460_SMTP_TLS_REPORTING.md)
- [RFC 8461 MTA-STS](RFC_8461_MTA_STS.md)
- [DNS Resilience Response](../playbooks/DNS_RESILIENCE_RESPONSE.md)
- [NIST SP 800-52 TLS Guidelines](NIST_SP_800_52_TLS_GUIDELINES.md)
