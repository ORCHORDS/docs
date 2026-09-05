---
title: "SMTP Version Governance (RFC 5321)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 5321; https://www.rfc-editor.org/rfc/rfc5321"
---

# SMTP Version Governance (RFC 5321)

## Scope

Reference card for the Simple Mail Transfer Protocol as defined by IETF RFC 5321. Used by mail, security, and operations teams when documenting outbound / inbound mail relay policy, message submission, DSN handling, or transport-layer authentication. Treats RFC 5321 as the authoritative protocol, with RFC 6409 (message submission), RFC 4954 (SMTP AUTH), RFC 3207 (STARTTLS), RFC 7817 (opportunistic DANE), RFC 8461 (MTA-STS), RFC 8460 (SMTP TLS Reporting), and RFC 9726 (DKIM-aligned DMARC) as companion documents.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 5321, "Simple Mail Transfer Protocol" |
| Status | Draft Standard; obsoletes RFC 2821 |
| Submission companion | RFC 6409 (port 587) |
| Companion AUTH | RFC 4954 |
| Companion STARTTLS | RFC 3207 |
| Verification source | https://www.rfc-editor.org/rfc/rfc5321 and IANA SMTP extensions / parameters |

## Plan

1. Identify the deployment context (originating MSA, internal relay, inbound MTA, outbound MTA, mail gateway with policy enforcement).
2. Map required behaviour against RFC 5321 § 3–§ 4 (procedural model, detailed operation: MAIL, RCPT, DATA, RSET, VRFY, NOOP, QUIT, TURN).
3. Capture operational requirements: TLS posture (RFC 3207 / RFC 8461), SMTP AUTH (RFC 4954), DSN / RFC 3461 handling, deliver-by retry cadence (RFC 5321 § 4.5.4), and queue management policy.
4. Validate against the live IANA registries (SMTP service extensions, status codes, enhanced status codes per RFC 3463).

## Inputs

- Envelope sender domain policy (SPF, DKIM, DMARC alignment, ARC per RFC 8617).
- Authentication posture (allow-listed AUTH mechanisms per RFC 4954: PLAIN over TLS, LOGIN, CRAM-MD5 over TLS).
- TLS policy (MTA-STS per RFC 8461, DANE per RFC 7672, SMTP TLS Reporting per RFC 8460).
- Outbound deliver-by cadence and retry policy (RFC 5321 § 4.5.4).
- Inbound policy: greylist, anti-spam, rate-limit, abuse handling, message-size cap.

## ORCHORDS Profile

This guide is used as a reference when reviewing mail deployment documentation or designing MTA policy. It does NOT introduce protocol behaviour beyond what the RFCs and IANA registries specify. When a behavioural rule that is not captured here is required by a mail operation, escalate to a fresh review against the current RFC and the relevant IANA registry.

## Implementation Notes

- Always enforce RFC 3207 STARTTLS on submission (port 587) and where peer MX advertises STARTTLS; combine with MTA-STS / DANE for stronger identity.
- Use enhanced status codes (RFC 3463) in DSNs; align retry semantics with RFC 5321 § 4.5.4 and RFC 8058 for one-click list-unsubscribe.
- For bulk senders, validate alignment per DMARC (RFC 7489), DKIM (RFC 6376), and SPF (RFC 7208); ARC (RFC 8617) is required when relaying through intermediaries.
- For ARC-sealed environments, also observe RFC 8617 § 5 limitations; never widen trust based on ARC chain depth alone.
- For inbound MX, prefer DNSSEC validating resolvers (RFC 4033) and RPKI-validated peer ASNs (RFC 6480 / RFC 8210) when filtering source networks.

## Companion Documents

- RFC 3461 (DSN extensions)
- RFC 3463 (Enhanced Status Codes)
- RFC 4954 (SMTP AUTH)
- RFC 5322 (Message Format)
- RFC 6376 (DKIM)
- RFC 6409 (Message Submission)
- RFC 7208 (SPF)
- RFC 7489 (DMARC)
- RFC 7817 (Opportunistic DANE)
- RFC 8461 (MTA-STS)
- RFC 8460 (SMTP TLS Reporting)
- RFC 8617 (ARC)
- RFC 9726 (DKIM-aligned DMARC)
- IANA SMTP Service Extensions / SMTP Status Codes / SMTP Enhanced Status Codes
