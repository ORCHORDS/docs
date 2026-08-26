# resource-hints-preconnect

**Issue:** Third-party origin connection latency delays resource loading
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
link rel=preconnect performs DNS lookup, TCP handshake, and TLS negotiation early for critical third-party origins. Saves 100-400ms per origin on first connection.

## Pattern / Solution
1. Preconnect to CDN: link rel=preconnect href=https://cdn.example.com.\n2. Preconnect to font origins: link rel=preconnect href=https://fonts.googleapis.com.\n3. Add crossorigin for CORS-required connections (fonts, API endpoints).\n4. Limit to 2-3 critical origins; more preconnects compete for network resources.\n5. Use dns-prefetch as a fallback for browsers that don't support preconnect.

## Gotchas
- Unused preconnected sockets are closed after 10 seconds, wasting CPU and memory.\n- Preconnect for every third party is counterproductive; profile first to find true bottlenecks.\n- crossorigin matters: a preconnect without it won't be reused for CORS requests.

## Related
dns-prefetch, resource-hints-preload, third-party-script-impact
