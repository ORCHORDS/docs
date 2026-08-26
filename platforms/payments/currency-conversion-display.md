# currency-conversion-display

**Issue:** Showing prices in the user's local currency while settling in a base currency
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users expect to see prices in their local currency, but charging in a foreign currency adds bank conversion fees and confusion. The display rate and the settlement rate may differ.

## Pattern / Solution
Detect user locale via IP geolocation or browser header. Look up cached FX rates. Show localized price with a disclaimer if charging in base currency. Alternatively use Stripe's presentment currency feature — charge in local currency, settle in USD via automatic conversion.

## Gotchas
Never guarantee the display price matches the billed amount if you are doing client-side conversion without locking the rate. Add a small buffer to cover rate fluctuations. Always display 'approximate' if rates are not locked at checkout.

## Related
multi-currency-handling, forex-rate-caching, price-rounding-rules
