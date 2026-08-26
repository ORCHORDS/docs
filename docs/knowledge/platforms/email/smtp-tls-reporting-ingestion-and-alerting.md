# SMTP TLS Reporting Ingestion and Alerting

**Issue:** MTA-STS and DANE failures can indicate downgrade attacks or ordinary configuration errors, but without TLS-RPT a receiving domain lacks aggregate evidence from sending MTAs.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Publish exactly one valid TXT policy at `_smtp._tls.<domain>` beginning with `v=TLSRPTv1` and one or more reviewed `rua` destinations using `mailto:` or `https:`. Separate report ingestion from user mail and apply size, rate, decompression, and parsing limits.

Accept the registered JSON/gzip or multipart report formats. For emailed reports, require the reporting domain's valid DKIM signature as RFC 8460 specifies. Parse as untrusted data: never render embedded values as HTML, execute them, resolve supplied hosts automatically, or use report values in shell/database expressions.

Deduplicate by reporting organization, policy domain, report ID, and date range. Aggregate success/failure counts by policy and failure type, preserve daily UTC windows, and baseline normal senders before paging. Correlate sudden certificate, DNS, MX, MTA-STS, or DANE failures with controlled configuration changes.

## Verification

Validate DNS lookup and split-string TXT handling. Feed valid JSON, gzip, multipart email, duplicate IDs, overlapping ranges, unknown fields, malformed and oversized payloads, compression bombs, invalid DKIM, and spoofed domains. Confirm alert thresholds catch a simulated certificate failure without paging on one low-volume reporter.

## Gotchas

Reports are delayed aggregate telemetry, not proof of individual-message confidentiality. Missing reports may reflect unsupported senders or an attacker blocking DNS discovery. Reports can disclose infrastructure details; restrict access and retention.

## Sources

- [RFC 8460: SMTP TLS Reporting](https://www.rfc-editor.org/rfc/rfc8460.html)
- [RFC 8461: MTA-STS](https://www.rfc-editor.org/rfc/rfc8461.html)
