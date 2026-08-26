# Internationalized DSN parsing and correlation

**Issue:** A bounce processor supports SMTPUTF8 delivery but rejects or corrupts UTF-8 addresses and diagnostics in internationalized delivery status notifications.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

RFC 6533 extends DSNs for internationalized mail. Parse structured MIME/status fields as UTF-8 where defined, retain recipient-level correlation, and preserve an ASCII-compatible operational path where required.

**Source:** [RFC 6533: Internationalized Delivery Status and Disposition Notifications](https://www.rfc-editor.org/rfc/rfc6533)

## Controls

- require correct report MIME structure before parsing fields;
- decode UTF-8 fields strictly with bounded error handling;
- correlate using opaque envelope IDs and original/final recipient fields;
- normalize only for the intended comparison, not by lowercasing arbitrary local parts;
- redact addresses/diagnostics from broad logs;
- make duplicate reports idempotent.

## Verification

Test UTF-8 local/domain parts, RTL, malformed UTF-8, mixed ASCII/internationalized fields, multi-recipient outcomes, duplicate/late reports, unknown correlation, and gateway downgrade. Final states must not regress.

## Gotchas

Human diagnostic text is not a classifier contract. An internationalized DSN can contain sensitive personal data. This is narrower than SMTPUTF8 transport support; every bounce-processing hop must also support it.
