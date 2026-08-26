# write-through-cache

**Issue:** Cache and database diverge after writes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A user updates their profile but the cached version persists, showing stale data for minutes.

## Pattern / Solution
Write to the cache and the database synchronously in the same write path. The application always writes through the cache layer. Reads always hit a warm cache. Consistency is maintained at the cost of write latency.

## Gotchas
Write-through increases write latency by the cache round-trip. For write-heavy workloads, this overhead may outweigh the benefits. Ensure the cache can handle the write throughput.

## Related
cache-aside-pattern, write-behind-cache, read-through-cache
