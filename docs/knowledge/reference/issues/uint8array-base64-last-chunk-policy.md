# Uint8Array Base64 Decoding Needs an Explicit Last-Chunk Policy

**Issue:** Base64 inputs can differ in alphabet, padding, trailing bits, and incomplete final chunks. Permissive decoding can make different strings map to the same bytes.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Select `base64` or `base64url` explicitly and set `lastChunkHandling` to the protocol's requirement.
- Use strict final-chunk validation for signed, hashed, canonical, or security-sensitive input.
- Cap decoded length before allocation and reject unexpected whitespace when the surrounding protocol forbids it.
- Canonicalize at one boundary and compare decoded bytes with timing-appropriate logic.

## Verification
- Test both alphabets, missing/excess padding, extra bits, whitespace, empty input, and truncated chunks.
- Round-trip canonical encodings and reject noncanonical alternatives where required.
- Fuzz decoder options against the protocol grammar.

## Gotchas
The ECMAScript decoder's configurable acceptance is not the same as a protocol's canonical encoding rule. Decoding success does not validate key, token, or file semantics.

## Official sources
- [ECMAScript Uint8Array.fromBase64](https://tc39.es/ecma262/multipage/indexed-collections.html#sec-uint8array.frombase64)
