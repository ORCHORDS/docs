# dns-prefetch

**Issue:** DNS resolution latency for third-party domains adds to load time
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
DNS lookups take 20-120ms. link rel=dns-prefetch resolves DNS for third-party origins in the background without opening a connection. Lighter than preconnect.

## Pattern / Solution
1. Add for all third-party origins used later in the page: analytics, fonts, APIs.\n2. link rel=dns-prefetch href=https://www.google-analytics.com.\n3. Use dns-prefetch for low-priority or uncertain third parties; preconnect for certain ones.\n4. Can be added dynamically from JavaScript before a third-party script loads.

## Gotchas
- dns-prefetch only resolves DNS; TCP and TLS still happen at first request time.\n- Browsers limit concurrent DNS lookups; too many hints may not all resolve.\n- Redundant with preconnect -- don't add both for the same origin.

## Related
resource-hints-preconnect, third-party-script-impact
