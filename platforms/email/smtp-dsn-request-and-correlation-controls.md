# SMTP DSN Request and Correlation Controls

**Issue:** Applications infer delivery from SMTP acceptance or parse human-readable bounce text, losing recipient-level state and sometimes generating unnecessary success or delay notifications.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

When the peer advertises the `DSN` EHLO capability, use RFC 3461 parameters deliberately: `RET` controls returned content, `ENVID` supplies an envelope identifier, `NOTIFY` selects SUCCESS, FAILURE, and/or DELAY for each recipient, and `ORCPT` preserves the original recipient. Generate opaque, non-secret ENVID values and maintain a bounded mapping to the internal send and recipient records.

Parse standards-based delivery reports as structured `multipart/report` / `message/delivery-status` data. Treat SMTP acceptance as transfer of responsibility, not evidence that a person read the message. Store recipient-level action, status, diagnostic code, reporting MTA, and original-recipient mapping; redact message content and addresses according to retention policy.

## Verification

Test peers that do and do not advertise DSN, multi-recipient transactions with mixed results, NOTIFY=NEVER, delayed and failed reports, unknown or expired ENVID values, duplicate reports, and malformed MIME. Confirm a duplicate DSN is idempotent and cannot regress a final state. Verify the client never sends DSN parameters to a peer that did not advertise support.

## Gotchas

NOTIFY=SUCCESS can generate high report volume and is not an open/read signal. ORCPT and returned headers can contain personal data. DSNs can be spoofed, so correlate conservatively and never use one as authorization for a sensitive action. Gatewayed mail may not preserve every requested semantic.

## Sources

- [IETF RFC 3461 — SMTP Service Extension for Delivery Status Notifications](https://datatracker.ietf.org/doc/html/rfc3461)
- [IETF RFC 3464 — Extensible Message Format for Delivery Status Notifications](https://datatracker.ietf.org/doc/html/rfc3464)
