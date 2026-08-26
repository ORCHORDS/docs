# Float16Array Introduces Binary16 Rounding Boundaries

**Issue:** Writing JavaScript Numbers to Float16Array or DataView narrows binary64 values to IEEE binary16, changing precision, range, signed zero, infinities, and NaN representation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Specify where binary16 storage is acceptable and round only at that boundary.
- Use `Math.f16round` to make expected narrowing explicit in tests and algorithms.
- Do not use Float16 for exact currency, counters, identifiers, or stable text round-trips.
- Preserve byte order explicitly with DataView.
- Define non-finite and signed-zero policy at serialization boundaries.

## Verification
- Test halfway cases, subnormals, min/max finite, overflow, underflow, both zeros, infinities, and NaN.
- Compare typed-array and DataView encodings in both byte orders.
- Round-trip representative model tensors against a binary16 oracle.

## Gotchas
Typed arrays store narrowed values even though reads return JavaScript Numbers. NaN payload details are not a portable data contract.

## Official sources
- [ECMAScript Float16Array and Math.f16round](https://tc39.es/ecma262/multipage/numbers-and-dates.html#sec-math.f16round)
