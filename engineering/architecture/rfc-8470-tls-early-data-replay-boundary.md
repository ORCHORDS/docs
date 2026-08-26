# Make TLS Early Data a Replay Boundary

**Issue:** TLS 1.3 early data can arrive before handshake completion and may be replayed. HTTP methods that look idempotent can still trigger non-idempotent application effects.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Disable early data by default and allowlist routes with proven replay-safe end-to-end behavior.
- Propagate and validate Early-Data across every intermediary as RFC 8470 specifies.
- Return 425 Too Early when the origin cannot safely process a request received in early data.
- Exclude authentication transitions, counters, reservations, rate-limit mutations, and secret-bearing responses.
- Bind deployment changes to replay-safety regression tests.

## Verification
- Capture and replay early requests across edge nodes and ticket lifetimes.
- Test intermediary retry, redirects, method overrides, and hidden side effects.
- Verify a 425 response causes a retry only after handshake completion.

## Gotchas
GET is safe by HTTP definition only when implemented without side effects. Anti-replay at one TLS terminator does not prove safety across a distributed deployment.

## Official sources
- [RFC 8470](https://www.rfc-editor.org/rfc/rfc8470.html)
- [RFC 8446 early-data security](https://www.rfc-editor.org/rfc/rfc8446.html#section-8)
