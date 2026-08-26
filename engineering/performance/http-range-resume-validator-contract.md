# HTTP Range Resume and Validator Contract

**Issue:** Large downloads restart from zero after interruption, or clients combine byte ranges from different representation versions and silently corrupt media or artifacts.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Advertise byte-range support accurately and return `206 Partial Content` with a correct `Content-Range` for satisfiable requests; return `416` with the current complete length for unsatisfiable ranges. Resume with `If-Range` using a strong ETag (or appropriate date validator), so a changed representation falls back to a complete `200` instead of combining mismatched bytes.

Keep representation selection stable across range requests: content coding, authorization, Vary dimensions, and object version must match the validator. Bound and normalize requested ranges, reject abusive overlap/multi-range patterns, and stream from storage without reading the full object when the backend supports safe range reads.

## Verification

Test prefix/suffix/open-ended ranges, last byte, beyond-end request, multiple ranges, interrupted resume, object replacement with same path, weak versus strong ETag, encoded and identity variants, cache/CDN behavior, authorization expiry, concurrent deletion, and range-amplification attempts. Hash the reassembled result against a full fetch.

## Gotchas

`Content-Length` on a 206 describes this message, not necessarily the whole object. Multiple ranges use `multipart/byteranges`. Partial responses are cacheable under HTTP rules but only safely combined with common strong validators. Range is not standardized partial PUT semantics.

## Sources

- [IETF RFC 9110 — HTTP Semantics, Range Requests](https://datatracker.ietf.org/doc/html/rfc9110#section-14)
- [IETF RFC 9111 — HTTP Caching](https://datatracker.ietf.org/doc/html/rfc9111)
