# cdn-cache-strategy

**Issue:** Origin server handles requests that CDN could serve from edge cache
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CDN cache misses add round trips to the origin. A well-configured CDN should handle 90%+ of traffic for static sites. Dynamic sites need careful cache-key design.

## Pattern / Solution
1. Set long s-maxage for static assets; short for HTML.\n2. Use cache-key normalization to avoid duplicate cache entries from query string variations.\n3. Implement stale-while-revalidate at the CDN level for HTML.\n4. Use Cloudflare Cache Rules or Fastly VCL to customize cache behavior per route.\n5. Monitor cache hit ratio in CDN analytics; target > 90% for static assets.

## Gotchas
- Cookies in requests bypass CDN caching by default; strip non-essential cookies at the edge.\n- Cache purging is eventual; account for propagation time during deployments.\n- Vary header (Vary: Accept-Encoding) can fragment cache; limit Vary fields.

## Related
cache-control-headers, edge-caching-patterns, cloudflare-workers-performance
