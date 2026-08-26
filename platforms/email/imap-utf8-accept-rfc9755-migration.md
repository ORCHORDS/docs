# IMAP UTF-8 acceptance and RFC 9755 migration

**Issue:** An IMAP client or server implements the obsolete RFC 6855 contract, assumes UTF-8 mailbox data is enabled for every IMAP4rev1 session, or sends an ENABLE argument that the current protocol no longer defines. Internationalized messages then fail only on particular server revisions or are decoded under the wrong mode.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

RFC 9755, published in March 2025, obsoletes RFC 6855 and defines UTF-8 support for IMAP. IMAP4rev2 includes UTF-8 support in its base behavior. An IMAP4rev1 connection instead uses advertised capabilities and the ENABLE mechanism described by the current specification.

This is the message-access layer of internationalized email. It does not replace SMTPUTF8 negotiation for message submission or delivery, nor does it by itself validate internationalized mailbox addresses.

## Controls and implementation

1. Determine the negotiated IMAP revision and capability set after authentication or any event that can change capabilities.
2. For IMAP4rev2, follow the revision's native UTF-8 rules. Do not send a legacy opt-in merely because older code did so for IMAP4rev1.
3. For IMAP4rev1, send ENABLE UTF8=ACCEPT only when the server advertises the corresponding capability and ENABLE is available. Confirm the enabled response before using the mode.
4. Do not implement UTF8=ONLY as an ENABLE argument. RFC 9755 removed the obsolete form from the earlier contract; preserve it only as an explicitly tested compatibility observation if a deployed peer still advertises legacy behavior.
5. Keep protocol tokens ASCII where the grammar requires them while allowing UTF-8 in the fields and message data the active mode permits. Apply the exact mailbox-name rules of the negotiated IMAP revision rather than a blanket string conversion.
6. Preserve raw server octets until the applicable response grammar identifies text. Decode strictly, surface malformed UTF-8 as a protocol/data error, and never repair it silently before audit.
7. Maintain a non-UTF-8 path for IMAP4rev1 servers that do not advertise support. A capability failure must not cause the client to send unnegotiated UTF-8.
8. Version capability cache entries by connection and invalidate them after STARTTLS, authentication, reconnect, or server greeting changes.

## Verification

Cover IMAP4rev2, IMAP4rev1 with and without ENABLE, UTF8=ACCEPT accepted and rejected, a legacy UTF8=ONLY advertisement, capability changes after login, malformed UTF-8, internationalized headers and bodies, mailbox names, SEARCH/FETCH round trips, and reconnects through a different backend.

Assert that an SMTPUTF8-delivered message remains retrievable without lossy header rewriting and that unsupported peers receive only the legacy-safe command form.

## Gotchas

- RFC 9755 is the current reference; implementing RFC 6855 literally can preserve obsolete behavior.
- SMTPUTF8 and IMAP UTF-8 solve different hops and must be negotiated separately.
- Unicode support does not remove MIME, transfer-encoding, normalization, or spoofing controls.
- Capability strings belong to a live connection, not a global provider profile.

## Official sources

- [RFC 9755 — Internet Message Access Protocol Support for UTF-8](https://www.rfc-editor.org/rfc/rfc9755.html)
- [RFC 9051 — Internet Message Access Protocol Version 4rev2](https://www.rfc-editor.org/rfc/rfc9051.html)
