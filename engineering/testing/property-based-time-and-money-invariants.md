# property-based-time-and-money-invariants

**Issue:** Tests use examples for date, currency, and amount logic but miss invariant violations across large input spaces.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Time and money bugs often occur at boundaries: precision, rounding, negative values, leap days, DST, conversion, and serialization. Property-based tests generate inputs to check invariants that example tests rarely cover, but failures need deterministic seeds and domain-aware generators.

## Fix

- define business invariants before generating values;
- generate decimals as integer minor units or fixed-precision values, never binary floating point for monetary rules;
- include boundary dates, zones, malformed values, and rounding edges;
- persist failing seeds and minimized cases as regressions;
- isolate provider/network calls and test deterministic domain logic locally;
- combine generated checks with specific known-production examples.

## Verification

- Monetary totals preserve the documented rounding invariant.
- Date/time conversion respects the selected instant/calendar policy.
- A discovered randomized failure reproduces from its stored seed.
- Invalid inputs fail safely without creating partial state.

## Related

- `testing/timezone-dst-boundary-regression-tests.md`
- `payments/nowpayments-minimum-amount-and-quote-preflight.md`
