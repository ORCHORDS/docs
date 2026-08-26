# forex-rate-caching

**Issue:** Caching foreign exchange rates efficiently for price display without stale data risk
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Fetching live FX rates on every page load is slow and expensive. Using stale rates can cause significant pricing errors. Free rate APIs have strict request limits.

## Pattern / Solution
Cache rates in Redis with a TTL of 1 hour. On cache miss, fetch from a provider such as exchangerate-api.com or Fixer.io. Store rates as a map from base currency to all targets. For checkout, lock the rate at session start and store the locked rate in the session.

## Gotchas
ECB publishes rates once per business day — suitable only for display, not settlement. Commercial providers update frequently but require paid plans. Always validate that the API response contains expected currencies before writing to cache.

## Related
currency-conversion-display, multi-currency-handling, price-rounding-rules
