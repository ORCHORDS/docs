# Intl.NumberFormat Explicit Rounding Policy

**Issue:** Default display rounding can disagree with financial, measurement, or regulatory rules, and formatted values can hide precision used by business logic.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Define rounding in the domain layer first, then configure `Intl.NumberFormat` to display the same policy. Choose `roundingMode` explicitly when ties or negative values matter; choose `roundingIncrement` for cash or measurement increments; and set fraction/significant digit limits intentionally. Use `trailingZeroDisplay:"stripIfInteger"` only when zeros do not convey precision.

Do calculations in an appropriate decimal/minor-unit representation rather than formatted strings or binary floating point for money. Never parse localized display text back into the authoritative amount. Inspect `resolvedOptions()` in diagnostics to expose implicit defaults.

`roundingIncrement` accepts a defined set of increments and cannot be combined with significant-digit rounding or a non-auto rounding priority. Validate formatter construction during startup/configuration rather than failing on a user request.

## Verification

Build boundary fixtures immediately below, at, and above every half increment; include positive/negative values, zero/negative zero, large/small magnitudes, currencies with different minor units, and multiple numbering systems. Assert both display and authoritative booked value. Test unsupported runtimes/polyfills and compare server/client output.

## Gotchas

Formatting rounding does not change the original Number. Default `halfExpand` may differ from accounting policy. Changing locale data or runtime can change literals but must not change the underlying booked amount.

## Sources

- [MDN Intl.NumberFormat constructor](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat)
- [ECMA-402 NumberFormat](https://tc39.es/ecma402/#numberformat-objects)
