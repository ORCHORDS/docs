# price-rounding-rules

**Issue:** Rounding currency amounts correctly to avoid off-by-one errors and audit failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
JavaScript floating-point math causes errors like 19.99 times 0.2 yielding unexpected fractions. Rounding after multiplication vs before causes discrepancies in tax calculations and invoice totals.

## Pattern / Solution
Store all amounts as integers in the smallest currency unit (cents for USD). Perform all arithmetic in integers. Only convert to decimal for display. Use Math.round() not Math.floor() for half-up rounding. For tax, round per line item and sum — not sum then round.

## Gotchas
Stripe API accepts amounts in smallest unit (cents). Some currencies are zero-decimal like JPY. Rounding 0.5 banker-style differs from standard — check your jurisdiction's requirements for tax.

## Related
multi-currency-handling, vat-calculation-eu, stripe-tax-calculation
