# redis-eviction-policies

**Issue:** Choosing the correct Redis maxmemory eviction policy to prevent OOM crashes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Redis hits `maxmemory` and either refuses writes (`noeviction`) causing application errors, or silently deletes data the application assumed was durable. Wrong policy choice causes cache stampedes or data loss.

## Pattern / Solution
Set `maxmemory` and `maxmemory-policy` explicitly — never rely on OS memory limits.

| Policy | Evicts | Use case |
|--------|--------|----------|
| `noeviction` | Nothing — returns error on write | Durable data store; never for cache |
| `allkeys-lru` | Any key, least recently used | General cache; recommended default |
| `allkeys-lfu` | Any key, least frequently used | Skewed access patterns (hot keys) |
| `volatile-lru` | Keys with TTL set, LRU order | Mix of durable + cached data in one Redis |
| `volatile-lfu` | Keys with TTL set, LFU order | Same as above but frequency-based |
| `volatile-ttl` | Keys with shortest remaining TTL | When you want soonest-expiring evicted first |
| `allkeys-random` | Any random key | Not recommended; unpredictable |

```redis
# redis.conf
maxmemory 4gb
maxmemory-policy allkeys-lru
maxmemory-samples 10   # higher = more accurate LRU, more CPU
```

```bash
# Check current policy at runtime
redis-cli CONFIG GET maxmemory-policy

# Change at runtime (persists until restart unless also in conf)
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

**Monitor eviction rate:**
```bash
redis-cli INFO stats | grep evicted_keys
# Prometheus exporter metric: redis_evicted_keys_total
```

Alert if eviction rate > 0 for caches that are supposed to be large enough; it means your `maxmemory` sizing is wrong.

## Gotchas
- `volatile-*` policies silently become `noeviction` for keys without TTL — if your application forgets to set TTL, writes will fail unexpectedly.
- LFU requires Redis 4.0+; the counter decays over time (controlled by `lfu-decay-time`).
- Eviction happens on write operations, not reads; a read-heavy workload can exceed `maxmemory` if writes are infrequent.
- `maxmemory` applies per Redis instance; in Cluster mode, multiply by the number of primary shards for total cluster capacity.

## Related
- `redis-sentinel-vs-cluster.md`
