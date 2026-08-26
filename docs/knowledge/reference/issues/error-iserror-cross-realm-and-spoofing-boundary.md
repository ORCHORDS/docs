# Error.isError Defines a Cross-Realm Brand Boundary

**Issue:** `instanceof Error` can reject genuine errors from another realm, while prototype or `toStringTag` checks can accept spoofed objects.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Use `Error.isError` where the supported runtime implements the standard and cross-realm brand detection is required.
- Keep structural validation for serialized error records separate from native Error recognition.
- Normalize untrusted thrown values into an application error envelope without executing getters.
- Feature-detect or provide a reviewed compatibility path for older runtimes.

## Verification
- Test native errors from same and different realms, subclasses, plain objects, proxies, and forged tags/prototypes.
- Throw primitives and hostile getter objects through normalization.
- Confirm the fallback has explicitly documented weaker semantics.

## Gotchas
A genuine Error is not necessarily safe to expose; message, cause, and stack may contain secrets. Serialized errors lose their native internal brand.

## Official sources
- [ECMAScript Error.isError](https://tc39.es/ecma262/multipage/fundamental-objects.html#sec-error.iserror)
