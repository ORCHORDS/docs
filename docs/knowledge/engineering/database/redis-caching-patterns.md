# redis-caching-patterns

**Issue:** Naive caching strategies lead to cache stampedes, stale data, or excessive memory usage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cache miss for a popular key causes hundreds of simultaneous DB queries. Cache memory growing unbounded.

## Pattern / Solution
Cache-aside (lazy loading): check cache, miss means load from DB then write to cache with TTL. Write-through: write to DB and cache atomically. Cache stampede prevention: Redis SET NX lock before regeneration. Set maxmemory-policy allkeys-lru for cache workloads.

## Gotchas
- Cache stampede (thundering herd): use distributed lock (SETNX + EXPIRE) or probabilistic expiration
- Cold start after Redis restart -- warm critical keys before opening traffic
- Serialization format affects performance: MessagePack faster than JSON for high-throughput caching

## Related
- redis-data-structures
- eventual-consistency-patterns
- read-replicas-routing
