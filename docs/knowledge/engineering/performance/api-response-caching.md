# api-response-caching

**Issue:** API endpoints recompute expensive results on every request
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Many API responses are cacheable -- user profiles, product catalogs, config data. Caching them in Redis or CDN eliminates database load and reduces latency.

## Pattern / Solution
1. Cache-aside pattern: check Redis first; on miss, query DB, store result, return.\n2. Set appropriate TTLs based on data freshness requirements.\n3. Use cache stampede prevention: distributed locks or probabilistic early expiration.\n4. Invalidate on write: delete or update the cache key when the underlying data changes.\n5. Cache at CDN edge for public, non-personalized API responses.

## Gotchas
- Over-caching leads to stale data; match TTL to business freshness requirements.\n- Cache keys must be unique per variation (user ID, locale, etc.).\n- JSON serialization/deserialization overhead can offset caching gains for tiny objects.

## Related
redis-pipeline-batching, cdn-cache-strategy, database-query-performance, api-response-compression
