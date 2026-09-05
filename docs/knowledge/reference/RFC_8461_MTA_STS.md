---
title: "RFC 8461 SMTP MTA Strict Transport Security"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 8461 (September 2018); https://www.rfc-editor.org/rfc/rfc8461"
---

# RFC 8461 SMTP MTA Strict Transport Security

## Scope

Reference card for IETF RFC 8461, *SMTP MTA Strict Transport Security (MTA-STS)* (September 2018). MTA-STS enables Mail Transfer Agents (MTAs) to enforce TLS when delivering email to a recipient domain, mitigating downgrade and interception attacks against SMTP. Profiles that govern inbound email security should reference RFC 8461 and bind it to RFC 8460 (TLSRPT), the DNS records that publish the policy, and the operational monitoring.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 8461 (September 2018) |
| Status | Proposed Standard |
| Companion | RFC 8460 (SMTP TLS Reporting — TLSRPT), RFC 4033 (DNSSEC), RFC 8555 (ACME), RFC 5280 (X.509 PKI) |
| Source URL | https://www.rfc-editor.org/rfc/rfc8461 |

## Plan

1. Reference RFC 8461 by version whenever a profile governs inbound email security.
2. Publish the MTA-STS DNS record at `_mta-sts.<domain>` with the policy version (v=STSv1) and the policy id.
3. Publish the MTA-STS policy file at `mta-sts.<domain>/.well-known/mta-sts.txt` over HTTPS, with the TLS version, the mode (enforce, testing, none), and the mx match patterns.
4. Select the mode: enforce (fail delivery to non-TLS endpoints) versus testing (report but accept) versus none (no enforcement).
5. Coordinate with RFC 8460 (TLSRPT) for reporting; configure the recipient-domain TLSRPT record at `_smtp._tls.<domain>`.
6. Operate an MTA that enforces the MTA-STS policy for inbound email.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- RFC 8461 normative sections: 3 (DNS records), 4 (policy file), 5 (TLS), 6 (interactions with DANE), 7 (interactions with TLSRPT).
- RFC 8460 TLSRPT normative sections.
- DNS zone management; HTTPS hosting for the policy file.
- Internal MTA configuration.

## ORCHORDS Profile

ORCHORDS treats RFC 8461 as the canonical reference for SMTP MTA-STS. Profiles that govern inbound email security should cite the RFC by version, identify the mode in operation (enforce, testing, none), and bind to RFC 8460 for reporting and to RFC 4033 if DNSSEC validation is part of the trust model.

A profile that references "email security" without binding to MTA-STS / DANE / TLSRPT is non-conformant.

## Implementation Notes

- MTA-STS policy version bumps trigger caching changes; coordinate the version bump with DNS and policy-file publication.
- The policy file is fetched over HTTPS; the certificate must be valid per the CA/Browser Forum Baseline Requirements.
- "enforce" mode may result in legitimate email being rejected during the initial deployment; use "testing" mode first.
- TLSRPT reports are diagnostic; do not treat them as authoritative until the recipient-side MTA is operating correctly.
- DNSSEC is not required for MTA-STS, but DNSSEC strengthens the trust model if available.

## Companion Documents

- [RFC 8460 SMTP TLS Reporting](RFC_8460_SMTP_TLS_REPORTING.md)
- [RFC 4033 DNSSEC Introduction](RFC_4033_DNSSEC_INTRODUCTION.md)
- [NIST SP 800-81 Secure DNS](NIST_SP_800_81_SECURE_DNS.md)
- [RFC 5280 X.509 PKI Profile](RFC_5280_X509_PKI_PROFILE.md)
- [DNS Resilience Response Playbook](../playbooks/DNS_RESILIENCE_RESPONSE.md)
