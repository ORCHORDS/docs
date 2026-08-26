# Set Methods Accept a Specific Set-Like Object Contract

**Issue:** New Set composition and relation methods accept set-like objects through `size`, `has`, and `keys`; they do not generically consume arbitrary iterables.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Pass actual Sets unless an adapter deliberately implements the set-record contract.
- Keep `size` a nonnegative numeric value and make `keys()` return an iterator of elements, not entries.
- Treat getters and methods on untrusted set-like objects as executable code.
- Snapshot inputs when mutation during comparison would violate application expectations.

## Verification
- Test Map, custom set-like objects, plain iterables without the contract, negative/NaN size, throwing getters, duplicate keys, and mutation during `has`.
- Verify relation and composition methods separately because their access patterns differ.

## Gotchas
Map is set-like because its `keys()` yields keys; a map's entries iterator would produce wrong elements. These operations are synchronous, not atomic.

## Official sources
- [ECMAScript Set methods and Set Records](https://tc39.es/ecma262/multipage/keyed-collections.html#sec-set-objects)
