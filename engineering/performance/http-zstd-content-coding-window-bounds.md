# HTTP zstd Content Coding and Window Bounds

**Issue:** A deployment enables Zstandard without negotiation, cache variation, or decoder memory bounds, causing unreadable responses, cache mixing, or excessive decompression memory.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Serve `Content-Encoding: zstd` only when the request advertises `zstd` in `Accept-Encoding`, and preserve `Vary: Accept-Encoding` wherever variants can share a cache key. Keep the original media type in `Content-Type`; content coding is representation encoding, not the `application/zstd` media type.

For HTTP interoperability follow RFC 9659: encoders must not generate frames requiring a window larger than 8 MB, while decoders must support up to that bound and reject oversized invalid frames safely. Precompress immutable assets where useful, select compression levels from measured ratio/CPU/latency, and retain Brotli/gzip/identity fallbacks.

## Verification

Test negotiation with every encoding order/q-value, intermediary recompression, correct Vary behavior, cold/warm cache, streaming decode, truncated/corrupt frames, oversized window, tiny and incompressible payloads, CPU saturation, and unsupported clients. Verify wire bytes and end-to-end latency, not ratio alone.

## Gotchas

Zstd support and CDN behavior can vary. Double compression wastes CPU and can corrupt semantics. High levels or windows can increase memory/latency. Do not compress already compressed media or secret-bearing responses mixed with attacker-controlled content without side-channel review.

## Sources

- [IETF RFC 8878 — Zstandard Compression](https://datatracker.ietf.org/doc/html/rfc8878)
- [IETF RFC 9659 — Window Sizing for Zstandard Content Encoding](https://datatracker.ietf.org/doc/html/rfc9659)
