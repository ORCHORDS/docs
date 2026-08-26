# SMTP RRVS recipient validity since

**Issue:** A long-lived sender transmits sensitive mail to an address that was deleted and later reassigned to a different person.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** standards-defined; support is not universal

RFC 7293 RRVS lets a sender state the earliest time from which it knows the recipient address was valid. A supporting receiver can reject delivery when mailbox ownership changed after that time.

**Source:** [RFC 7293: Require-Recipient-Valid-Since Header Field and SMTP Service Extension](https://www.rfc-editor.org/rfc/rfc7293)

## Controls

- derive the timestamp from verified recipient/account history, not message creation time;
- send the SMTP parameter only when advertised and preserve the header where appropriate;
- define policy by message sensitivity and an explicit unsupported-peer fallback;
- treat rejections as address-identity risk, not a generic transient bounce;
- minimize stored recipient-history metadata.

## Verification

Test unchanged address, reassigned address, unknown history, malformed/future timestamps, unsupported relays, forwarding, mailing lists, clock skew, and DSN correlation. Confirm ordinary mail is not globally blocked by missing support.

## Gotchas

RRVS cannot prove the current human identity and does not protect against a compromised existing mailbox. Forwarding/gateway behavior can reduce assurance. Do not synthesize a false “valid since” time.
