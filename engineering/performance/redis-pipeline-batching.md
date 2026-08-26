# redis-pipeline-batching

**Issue:** Multiple Redis commands execute serially with redundant round trips
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Each Redis command incurs a network round trip (~0.1-1ms). Pipelining sends multiple commands in one batch and receives all responses together.

## Pattern / Solution
1. Using ioredis: const pipeline = redis.pipeline(); keys.forEach(key => pipeline.get(key)); const results = await pipeline.exec().\n2. Use multi() for atomic transactions (MULTI/EXEC).\n3. Use mget/mset for simple batch get/set operations.\n4. Use Lua scripts with eval for atomic multi-key operations.

## Gotchas
- Pipelines are not atomic; use MULTI/EXEC if atomicity is required.\n- Very large pipelines (>10,000 commands) can overwhelm Redis; batch in chunks.\n- Pipeline errors return per-command; check each result for errors.

## Related
api-response-caching, database-query-performance, kv-read-performance
