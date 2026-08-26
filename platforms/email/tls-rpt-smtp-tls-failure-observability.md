# SMTP TLS reporting observability

**Issue:** A domain publishes MTA-STS or relies on SMTP TLS but has no visibility into delivery failures caused by TLS negotiation, certificate, DNS, or policy problems.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

TLS-RPT lets a domain request aggregated reports about SMTP TLS connection failures. It improves observability; it does not itself enforce encryption or replace MTA-STS/DANE policy.

**Source:** [RFC 8460 — SMTP TLS Reporting](https://www.rfc-editor.org/rfc/rfc8460.html)

## Operating pattern

- publish a TLS-RPT DNS record with a monitored, access-controlled aggregate-report destination;
- correlate report findings with MTA-STS/DANE policy changes, certificate renewal, and mail-delivery metrics;
- validate report parsing and retention; treat reports as potentially sensitive operational data;
- alert on sustained failure classes and investigate destination/domain patterns before changing enforcement;
- separate monitoring/reporting endpoints from inbound customer email processing.

## Verification

- DNS record syntax and report endpoint ownership are validated;
- a controlled TLS/policy failure produces an interpretable aggregate report;
- report ingestion rejects malformed/untrusted payloads safely and does not expose report contents publicly;
- certificate and MTA-STS changes are checked against delivery outcomes;
- no report alone is treated as proof that every sender enforced TLS.

## Gotchas

- TLS-RPT is reporting, not transport security enforcement.
- Aggregates can reveal sending infrastructure and delivery patterns; restrict access and retention.
- Not every sender supports it, so absence of reports is not proof of success.
- Do not route report mail into an automated mailbox that can execute attachments or untrusted workflows.

## Related

- `the MTA-STS guidance in email/security/`
- `email/dmarc-ruf-forensic.md`
- `security/tls-13-early-data-0rtt-replay-safe-endpoint-policy.md`
