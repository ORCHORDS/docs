# multi-currency-handling

**Issue:** Supporting payments in multiple currencies without double-charging or currency mismatches
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe requires the charge currency to match the customer's bank currency for zero-decimal handling. Presenting prices in local currency while charging in USD causes confusion and potential disputes.

## Pattern / Solution
Store prices in your base currency (USD). At display time, convert using a cached FX rate with a small markup buffer. For Stripe, use presentment currency with automatic_payment_methods. For subscriptions, set the subscription currency at creation time and never change it.

## Gotchas
Stripe subscriptions lock currency at creation — you cannot change it later. Zero-decimal currencies like JPY must have amounts without decimal points. EUR payments in Europe prefer SEPA; offering card-only limits conversion.

## Related
currency-conversion-display, forex-rate-caching, price-rounding-rules, stripe-sepa-debit
