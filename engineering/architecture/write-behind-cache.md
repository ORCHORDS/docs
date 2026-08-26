# write-behind-cache

**Issue:** Write latency is too high when writing to both cache and database synchronously
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A leaderboard update path is too slow because every write must synchronously persist to the database before acknowledging the client.

## Pattern / Solution
Write to the cache immediately and acknowledge the client. Asynchronously flush cache writes to the database in batches. Reduces write latency at the cost of potential data loss on cache failure.

## Gotchas
Data loss window exists between cache write and database flush. Do not use write-behind for financial or audit-critical data. The async flush must include retry logic and a dead-letter queue.

## Related
write-through-cache, cache-aside-pattern, outbox-pattern
