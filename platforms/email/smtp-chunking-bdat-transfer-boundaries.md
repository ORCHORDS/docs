# SMTP CHUNKING and BDAT Transfer Boundaries

**Issue:** Large or binary messages are sent with `DATA` assumptions even when a peer advertises CHUNKING, causing buffering, dot-stuffing mistakes, ambiguous partial failures, or an invalid attempt to use BINARYMIME without its prerequisites.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Treat ESMTP capabilities as per-connection facts. Send `EHLO`, parse the complete multiline response, and use `BDAT` only when `CHUNKING` is advertised. Each BDAT command declares an exact octet count; `LAST` terminates the message. Do not pipeline the next transaction until the final chunk response establishes acceptance.

CHUNKING alone does not authorize arbitrary binary content. Use BINARYMIME only when the peer advertises it, and preserve MIME/content-transfer rules otherwise. Keep a DATA fallback because a CHUNKING server must still support DATA. Record whether the transaction used DATA or BDAT, chunk sizes, final SMTP reply class, and the peer capability set without logging message bodies.

## Verification

Exercise DATA fallback, one-chunk BDAT, multiple chunks, zero-length final chunks, exact boundary sizes, connection loss between chunks, and a 4xx/5xx response to a non-final and final chunk. Confirm byte counts are measured after transport serialization. Verify retry logic starts a new SMTP transaction and never assumes an interrupted partial BDAT message was accepted.

## Gotchas

BDAT removes DATA dot-stuffing; applying both corrupts content. A successful intermediate chunk response is not final message acceptance. Capability advertisements can change after STARTTLS, so issue EHLO again. Chunking may reduce buffering, but it does not override server message-size limits or create application-level resumability.

## Sources

- [IETF RFC 3030 — SMTP CHUNKING and BINARYMIME](https://datatracker.ietf.org/doc/html/rfc3030)
- [IETF RFC 5321 — Simple Mail Transfer Protocol](https://datatracker.ietf.org/doc/html/rfc5321)
