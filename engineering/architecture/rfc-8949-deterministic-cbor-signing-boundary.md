# RFC 8949 deterministic CBOR signing boundary

**Issue:** Equivalent CBOR data can have multiple encodings, breaking byte signatures and hashes.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Define deterministic encoding profile, map-key ordering, float/NaN and duplicate-key policy before signing.

## Tests

Canonical vectors, alternate encodings, duplicate keys, indefinite lengths, NaNs.

## Gotchas

Well-formed CBOR is not necessarily deterministic; decode/re-encode may change signed bytes.

## Official sources

- https://www.rfc-editor.org/rfc/rfc8949
