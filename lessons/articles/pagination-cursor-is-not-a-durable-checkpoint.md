# A Pagination Cursor Is Not a Durable Checkpoint

**Issue:** Opaque page tokens can expire and are normally valid only for the original query. Persisting one as a long-term synchronization checkpoint can strand a job or silently change the scanned set.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use a page token only to continue the same short-lived traversal with unchanged filters and ordering.
- Store a domain checkpoint—such as a stable high-water mark plus tie-breaker—for resumable ingestion.
- Bind transient cursor state to a hash of the request parameters and reject mismatched resumes.
- Define cursor-expiry recovery from a safe domain checkpoint, with idempotent writes and deduplication.
- Treat the absence of a next token, not a short or empty page, as end of collection.

## Verification

- Expire a token between pages and confirm the job restarts without gaps or duplicate side effects.
- Mutate the collection during traversal and measure omission/duplication behavior.
- Change one request filter and assert the saved cursor is refused.
- Test zero-item pages that still contain a continuation token.

## Gotchas

Base64 does not make a cursor stable or safe to interpret. A token indicates where the server can continue a particular pagination process; it is not authorization and it need not encode a permanent record position.

## Official sources

- [Google AIP-158: Pagination](https://google.aip.dev/158)
