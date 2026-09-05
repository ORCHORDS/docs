---
title: "RFC 8460 SMTP TLS Reporting"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 8460 (September 2018); https://www.rfc-editor.org/rfc/rfc8460"
---

# RFC 8460 SMTP TLS Reporting

## Scope

Reference card for IETF RFC 8460, *SMTP TLS Reporting (TLSRPT)* (September 2018). TLSRPT defines a reporting mechanism for sending domains to receive diagnostic information about TLS negotiation success and failure when delivering email. Profiles that govern inbound email security should reference RFC 8460 alongside RFC 8461 (MTA-STS) and the DNS records that publish the policy.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 8460 (September 2018) |
| Status | Proposed Standard |
| Companion | RFC 8461 (MTA-STS), RFC 4033 (DNSSEC), RFC 8555 (ACME), RFC 5280 (X.509 PKI) |
| Source URL | https://www.rfc-editor.org/rfc/rfc8460 |

## Plan

1. Reference RFC 8460 by version whenever a profile governs inbound email security.
2. Publish the TLSRPT DNS record at `_smtp._tls.<domain>` with the reporting endpoint (mailto: or https: URI).
3. Operate a TLSRPT receiver that can ingest, parse, and act on TLSRPT reports.
4. Coordinate with RFC 8461 (MTA-STS): TLSRPT is the feedback channel for MTA-STS enforcement.
5. Treat TLSRPT reports as diagnostic; verify any reported failures before acting.
6. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- RFC 8460 normative sections: 3 (DNS records), 4 (report format), 5 (report delivery), 6 (privacy considerations).
- RFC 8461 (MTA-STS) companion guidance.
- DNS zone management; TLSRPT receiver (https: URI hosted endpoint, or mailto: with parsing).
- Internal incident-response workflow for TLS negotiation failures.

## ORCHORDS Profile

ORCHORDS treats RFC 8460 as the canonical reference for SMTP TLS reporting. Profiles that govern inbound email security should cite the RFC by version, identify the reporting endpoint, and bind to RFC 8461 (MTA-STS).

A profile that references "TLS reporting" or "email security" without binding to TLSRPT / MTA-STS is non-conformant.

## Implementation Notes

- TLSRPT reports are sent to the URI in the DNS record; the receiver must be configured to accept reports from sending MTAs.
- TLSRPT reports use application/tlsrpt+json or application/tlsrpt+gzip; the receiver should accept both.
- Reports may be delayed by sending MTAs; treat missing reports as ambiguous, not as a positive signal.
- Privacy: TLSRPT reports contain sender and recipient information; the receiver should treat them as restricted data.
- TLSRPT complements MTA-STS but does not enforce TLS; enforcement is in MTA-STS.

## Companion Documents

- [RFC 8461 SMTP MTA Strict Transport Security](RFC_8461_MTA_STS.md)
- [RFC 4033 DNSSEC Introduction](RFC_4033_DNSSEC_INTRODUCTION.md)
- [RFC 5280 X.509 PKI Profile](RFC_5280_X509_PKI_PROFILE.md)
- [DNS Resilience Response Playbook](../playbooks/DNS_RESILIENCE_RESPONSE.md)
