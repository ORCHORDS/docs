# NOWPayments Minimum Amount and Estimate Validity

**Issue:** A crypto quote can fall below the route-specific minimum or expire before payment creation, leading to underpayment, unexpected fees, or a customer sending an obsolete amount.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

After the customer selects a pay currency, request the minimum amount for the exact currency-from/currency-to pair and the same fixed-rate and fee-paid-by-user flags intended for payment creation. Request the estimated price and ensure it clears that matching minimum with a product-defined safety policy before presenting it.

Treat estimates as time-bound display data, not booked settlement. Bind the shown amount to currency, network, flags, quote/expiration time, order ID, and provider payment ID. At creation, use current provider values; if the estimate expires, refresh and require the user to acknowledge material changes. Use the documented payment-estimate update behavior and status API rather than recalculating from a public market price.

Keep decimal values as strings or decimal types with asset-specific precision. Never fulfill from the success redirect or estimate; use verified provider status and the existing payment-state control.

## Verification

Test amounts below, equal to, and above minimum; fixed versus variable rate; fee-payer variants; currency/network changes; estimate expiration; refresh before/after expiration; rapid volatility; unsupported pair; API timeout; partial payment; and duplicated order submission. Confirm UI labels distinguish approximate quote, exact send amount, and actual received/outcome amount.

## Gotchas

Minimums and network fees are dynamic and flow-specific. An estimate is not a guarantee. Fiat “price currency” is a valuation input and does not imply fiat settlement.

## Sources

- [NOWPayments API minimum amount and estimated price](https://documenter.getpostman.com/view/7907941/2s93JusNJt)
- [NOWPayments payment integration](https://nowpayments.io/payment-integration)
