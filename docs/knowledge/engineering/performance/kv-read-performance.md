# kv-read-performance

**Issue:** KV reads are slower than expected or causing latency
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare KV is eventually consistent with global replication. Reads hit the nearest edge PoP with a local cache; writes propagate in 60 seconds.

## Pattern / Solution
1. Use cacheTtl option to leverage edge cache: kv.get(key, { cacheTtl: 3600 }).\n2. Store computed values in KV to avoid recomputation in Workers.\n3. Batch multiple KV reads with Promise.all() since they are async.\n4. Use KV for config, feature flags, and semi-static data -- not for high-frequency writes.\n5. Keep values small (< 10 KB); large values increase read latency.

## Gotchas
- KV write to read consistency can take up to 60 seconds across regions. Don't read your own writes immediately.\n- KV has a free tier limit of 100,000 reads/day; monitor usage to avoid unexpected charges.\n- KV is not suitable for counters or anything requiring strong consistency; use Durable Objects instead.

## Related
cloudflare-workers-performance, edge-caching-patterns, redis-pipeline-batching
