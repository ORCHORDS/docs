# Compression Streams with bounded browser processing

**Issue:** Buffering an entire export or upload before compression increases peak memory and can freeze the main thread. Hand-rolled compression wrappers also mishandle stream errors and format negotiation.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Where supported, compose `CompressionStream` or `DecompressionStream` with Web Streams so backpressure bounds memory. Restrict formats to those the platform declares and keep server-side processing as the compatibility path.

## Controls

- Feature-detect constructors and the intended format.
- Set explicit uncompressed and compressed byte limits.
- Enforce an expansion-ratio ceiling during decompression to resist compression bombs.
- Propagate cancellation and errors through the full pipeline.
- Never infer content safety from successful decompression; validate the resulting media or document independently.
- Keep cryptographic verification over the canonical bytes defined by the protocol.
- Run CPU-heavy generation away from user-critical main-thread work when possible.
- Do not apply compression twice to already compressed media.

## Verification

Test empty, tiny, large, truncated, corrupt, adversarially expanding, and canceled streams. Measure peak memory, main-thread delay, throughput, and output interoperability against an independent implementation. Confirm unsupported clients take the server path and that a consumer stopping early cancels upstream work.

## Gotchas

Backpressure limits queued chunks but does not create a universal safety limit. Compression can expose length side channels when attacker-controlled and secret material share a context. Supported format names are constrained by the specification; do not pass arbitrary codec labels.

## Sources

- [Compression Streams Living Standard](https://compression.spec.whatwg.org/)
- [WHATWG Streams Living Standard](https://streams.spec.whatwg.org/)
