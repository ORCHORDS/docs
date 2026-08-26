# SMTPUTF8 Capability and Downgrade Boundaries

**Issue:** Internationalized mailbox local parts and UTF-8 headers cannot be safely sent through a relay that does not advertise SMTPUTF8; naive ASCII conversion can misdeliver mail.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

After EHLO, require the peer's `SMTPUTF8` capability before sending a MAIL command with the SMTPUTF8 parameter or a message containing internationalized addresses/headers governed by RFC 6532. If absent, do not transmit that message. Return a clear nondelivery or use an alternate address explicitly supplied and verified by the user; do not invent a downgrade for a non-ASCII local part.

Treat domain internationalization separately: IDNA A-label conversion can represent an internationalized domain, but it cannot convert a Unicode mailbox local part. Store the canonical mailbox and display form without lossy case or Unicode normalization assumptions. Apply anti-spoofing review to confusable domains and addresses.

## Verification

Test ASCII-only, Unicode domain with ASCII local part, Unicode local part, mixed headers, DSNs, forwarding, aliases, mailing lists, and relays that add/remove capability. Validate wire bytes and SMTP response handling with supporting and nonsupporting servers. Test normalization variants as distinct inputs unless the owning mail system defines equivalence.

## Gotchas

SMTPUTF8 support on the first hop does not prove every downstream route supports it. Unicode display increases homograph risk. An address that looks equivalent to a user can be operationally distinct.

## Sources

- [RFC 6531: SMTP Extension for Internationalized Email](https://www.rfc-editor.org/rfc/rfc6531.html)
- [RFC 6532: Internationalized Email Headers](https://www.rfc-editor.org/rfc/rfc6532.html)
- [RFC 5890: IDNA definitions](https://www.rfc-editor.org/rfc/rfc5890.html)
