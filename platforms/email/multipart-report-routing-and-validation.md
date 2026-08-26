# Multipart report routing and validation

**Issue:** Automated mail reports use `multipart/report` to pair human-readable text with a machine-readable report. Parsing only the visible part, trusting the declared report type, or recursively triggering reports can misclassify delivery/security events and create loops.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation
Parse MIME boundaries under strict depth/size limits and require the `report-type` parameter to match the machine-readable part actually present. Preserve the complete original message as evidence. Dispatch DSN, MDN, feedback, and other reports to type-specific validators; never execute actions from the human-readable part. Correlate through authenticated local message identifiers and envelope records, not attacker-supplied display headers.

Suppress automatic responses to reports and messages marked auto-generated. Deduplicate by stable report/message evidence and keep parse failure quarantined rather than guessing.

## Verification
Test missing/mismatched report types, reordered/duplicate parts, nested reports, malformed boundaries, oversized original-message parts, forged identifiers, unknown extensions, and response loops.

## Gotchas
Multipart/report is a framework, not a single event schema. MIME validity does not establish authenticity or business truth.

## Sources
- RFC Editor, [RFC 3462 — Multipart/Report](https://www.rfc-editor.org/rfc/rfc3462.html)
- RFC Editor, [RFC 5322 — Internet Message Format](https://www.rfc-editor.org/rfc/rfc5322.html)
