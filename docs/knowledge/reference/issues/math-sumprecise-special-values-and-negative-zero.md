# Math.sumPrecise Has Special-Value and Negative-Zero Semantics

**Issue:** Replacing a reduction with `Math.sumPrecise` improves varying-magnitude summation but also changes iterator, type, infinity, NaN, empty-input, and signed-zero behavior.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Specify accepted element types and handling of non-finite values before adoption.
- Preserve order-independent business expectations only after testing the domain; do not imply exact decimal arithmetic.
- Decide whether signed zero is observable in downstream division, serialization, or comparison.
- Keep decimal money and exact integer aggregation in domain-appropriate representations.
- Feature-detect the runtime and avoid an unqualified naive-reduce fallback.

## Verification
- Test empty input, only negative zero, mixed signed zeros, cancellation, huge/small magnitudes, NaN, both infinities, non-number elements, and iterator throws.
- Compare against a high-precision oracle within a documented rounding policy.
- Verify iterator closure on abrupt completion.

## Gotchas
“Precise” means more accurate floating-point summation under the specified algorithm, not arbitrary precision. Special values can dominate the result.

## Official sources
- [ECMAScript Math.sumPrecise](https://tc39.es/ecma262/multipage/numbers-and-dates.html#sec-math.sumprecise)
