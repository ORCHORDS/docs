# Resource Timing body-size interpretation

**Issue:** `transferSize`, `encodedBodySize`, and `decodedBodySize` are often divided into a “compression ratio,” but caches, headers, cross-origin filtering, zero-length responses, service workers, and content encoding make that ratio ambiguous.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Preserve all three raw fields with initiator, delivery type, status, content encoding, browser/version, and timing-allow visibility. Compute derived ratios only when denominators are positive and the sample is not filtered. Separate network transfer overhead, encoded payload, and decoded representation; do not interpret cache zero transfer as infinite compression.

Cohort service-worker and cross-origin resources separately. Increase/observe buffers deliberately and redact resource URLs before export.

## Verification

Test cold/warm/validated cache, gzip/Brotli/identity, 204/304/HEAD, zero-byte bodies, cross-origin with/without Timing-Allow-Origin, service-worker synthetic responses, redirects, streaming, and unsupported/filtered values.

## Gotchas

Transfer size includes protocol-dependent overhead and may be zero for cache or privacy reasons. Decoded size is not JavaScript heap cost, image decoded pixels, or proof the response was useful.

## Sources

- W3C Web Performance WG, [Resource Timing](https://www.w3.org/TR/resource-timing/)
- IETF, [HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
