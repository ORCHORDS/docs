# cache-hit-rate-monitoring

**Issue:** Tracking cache effectiveness to detect cache invalidation bugs or warming failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Database load unexpectedly high after deployment. Cache hit rate dropped silently.

## Pattern / Solution
Export Redis/Memcached metrics via redis_exporter. Key metric: keyspace_hits divided by total lookups = hit rate. Alert when hit rate drops below 80% (tune to your baseline). Track evicted_keys — evictions indicate memory pressure. Monitor used_memory vs maxmemory. Instrument application-level caching as counters and expose via /metrics.

## Gotchas
Cache hit rate varies by key pattern — aggregate hit rate can hide specific cold caches. After a deployment changing cache keys you will see a cold start period — suppress hit rate alerts for 5min after deployments. TTL spread randomization prevents thundering herd when many keys expire simultaneously.

## Related
connection-pool-monitoring, queue-depth-monitoring, database-query-monitoring
