---
title: "NIST SP 800-81 Secure DNS Deployment Guide"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-81-2 (September 2013, includes updates); https://csrc.nist.gov/publications/detail/sp/800-81/2/final"
---

# NIST SP 800-81 Secure DNS Deployment Guide

## Scope

Reference card for NIST Special Publication 800-81-2, *Secure Domain Name System (DNS) Deployment Guide* (September 2013, with subsequent updates). The publication remains the canonical NIST reference for secure DNS deployment. Profiles that govern DNS infrastructure should reference SP 800-81-2 and bind it to RFC 4033 (DNSSEC), RFC 8461 (MTA-STS), RFC 8460 (TLSRPT), and the operational monitoring.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-81-2 (September 2013, with updates) |
| Status | Final; current edition |
| Companion artifacts | RFC 4033/4034/4035 (DNSSEC), RFC 6781 (DNSSEC operational practices), RFC 7583 (DS digest algorithms), RFC 8460/8461 (MTA-STS/TLSRPT) |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-81/2/final |

## Plan

1. Reference SP 800-81-2 by version whenever a profile governs DNS infrastructure.
2. Apply the SP 800-81-2 deployment guidance: authoritative server hardening, recursive resolver hardening, registry configuration, and DNSSEC signing where applicable.
3. Bind to RFC 4033/4034/4035 for DNSSEC signing and validation.
4. Bind to RFC 6781 for DNSSEC operational practices (key rollover, signature validity, algorithm deprecation).
5. Bind to RFC 8460/8461 for MTA-STS and TLSRPT (DNS side).
6. Treat DNS as a high-value asset; monitor for unauthorized changes, configuration drift, and availability degradation.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- SP 800-81-2 normative sections: 3 (threats), 4 (deployment), 5 (operations), 6 (DNSSEC), appendices.
- RFC 4033/4034/4035 (DNSSEC), RFC 6781 (operational practices), RFC 7583 (DS digest algorithms).
- Internal DNS architecture, zone inventory, and key-rollover schedule.

## ORCHORDS Profile

ORCHORDS treats SP 800-81-2 as the canonical NIST reference for secure DNS deployment. Profiles that reference DNS security should cite the standard by version, identify the deployment model (authoritative, recursive, or both), and bind to RFC 4033 and RFC 6781.

A profile that references "DNS security" without binding to a recognized framework is non-conformant.

## Implementation Notes

- Authoritative DNS servers should be hardened with minimal software, restricted zones, and restricted access.
- Recursive resolvers should validate DNSSEC if upstream authoritative servers are signed; the trust anchors should be maintained.
- Key rollover should be planned per RFC 6781 with milestones; unplanned rollovers can cause widespread validation failures.
- DNS over HTTPS (RFC 8484) and DNS over TLS (RFC 7858) are privacy-preserving recursive resolution protocols; treat them as supplements to validation, not replacements.
- Monitoring should detect zone changes, key changes, and configuration drift; ad-hoc monitoring is non-conformant.

## Companion Documents

- [RFC 4033 DNSSEC Introduction](RFC_4033_DNSSEC_INTRODUCTION.md)
- [RFC 8460 SMTP TLS Reporting](RFC_8460_SMTP_TLS_REPORTING.md)
- [RFC 8461 SMTP MTA Strict Transport Security](RFC_8461_MTA_STS.md)
- [DNS Resilience Response Playbook](../playbooks/DNS_RESILIENCE_RESPONSE.md)
