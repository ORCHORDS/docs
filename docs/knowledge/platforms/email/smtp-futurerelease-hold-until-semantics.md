# SMTP FUTURERELEASE hold-until semantics

**Issue:** Scheduled email is handed to a relay with only an application timer, or FUTURERELEASE is mistaken for guaranteed delivery at an exact instant.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

RFC 4865 lets an advertising server accept a message for future release via the MAIL FROM `HOLDFOR` or `HOLDUNTIL` parameter. It controls when the server may release the message; it does not guarantee final delivery time.

**Source:** [RFC 4865: SMTP Submission Service Extension for Future Message Release](https://www.rfc-editor.org/rfc/rfc4865)

## Controls

- use only after EHLO advertises FUTURERELEASE;
- validate advertised maximum delay and supported timestamp form;
- store the product schedule, submission result, and server queue identifier durably;
- define fallback for unsupported or rejected requests;
- make resubmission idempotent and expose cancellation limitations honestly.

## Verification

Test relative and absolute requests, boundary delay, past time, clock skew, DST display, reconnect ambiguity, unsupported peers, and DSNs. Verify release means relay processing begins, not inbox arrival.

## Gotchas

This extension belongs at message submission, not arbitrary relay assumptions. Server retention and abuse policy still apply. Cancellation or modification is not supplied by FUTURERELEASE itself.
