# cache-control-headers

**Issue:** Resources are re-downloaded on repeat visits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Proper Cache-Control headers eliminate network requests for unchanged assets. Wrong headers force revalidation on every visit or prevent caching entirely.

## Pattern / Solution
1. Immutable static assets (fingerprinted): Cache-Control: public, max-age=31536000, immutable.\n2. HTML documents: Cache-Control: no-cache (revalidates each time but uses ETag).\n3. API responses: Cache-Control: private, max-age=60 or no-store for sensitive data.\n4. Use content-hash file names to bust cache safely.\n5. stale-while-revalidate=86400 allows serving stale content while revalidating in background.

## Gotchas
- no-cache does NOT mean don't cache -- it means revalidate before serving from cache.\n- no-store truly prevents caching; use only for sensitive data.\n- CDN caches ignore private; use s-maxage to set CDN TTL separately from browser TTL.

## Related
etag-conditional-requests, cdn-cache-strategy, service-worker-cache-strategy
