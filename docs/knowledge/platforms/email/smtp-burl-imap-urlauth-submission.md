# SMTP BURL and IMAP URLAUTH submission boundary

**Issue:** A submission client downloads a large message from an IMAP store only to upload identical bytes to the submission server, or exposes a reusable storage credential to avoid the copy.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** standards-defined; capability-dependent

RFC 4468 BURL lets an SMTP submission server fetch message content identified by an authorized URL, commonly IMAP URLAUTH. Treat the URL as a short-lived bearer capability and preserve exact message assembly semantics.

**Sources:** [RFC 4468: Message Submission BURL Extension](https://www.rfc-editor.org/rfc/rfc4468) · [RFC 4467: IMAP URLAUTH](https://www.rfc-editor.org/rfc/rfc4467)

## Controls

- use BURL only after EHLO advertises it and only over authenticated, protected submission;
- mint least-scope, short-expiry, single-purpose URLAUTH material;
- validate declared LAST ordering and message-size limits;
- prevent URLs, credentials, and message content from logs;
- define DATA fallback without silently duplicating a transaction.

## Verification

Exercise unsupported capability, expired/revoked URL, wrong mailbox/object, partial assembly, multiple BURL segments, LAST, fetch timeout, size rejection, ambiguous disconnect, and replay. Verify storage authorization cannot be broadened by URL editing.

## Gotchas

BURL is not arbitrary server-side URL fetching. A leaked URLAUTH token can disclose mail content. Successful retrieval still requires final SMTP message acceptance.
