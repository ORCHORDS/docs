# redis-data-structures

**Issue:** Using only Redis strings when richer data structures would be more efficient
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Storing JSON blobs as strings and parsing on every read. Multiple string keys for data that belongs together.

## Pattern / Solution
Strings: simple values, counters (INCR). Hashes: object fields (HSET user:1 name Alice age 30). Lists: queues (LPUSH/RPOP). Sets: unique members, tags (SADD, SISMEMBER). Sorted Sets: leaderboards (ZADD with score). HyperLogLog: cardinality estimation. Streams: append-only log. Choose based on access pattern.

## Gotchas
- Large hashes with many fields are encoded as ziplist up to hash-max-ziplist-entries -- memory efficient
- KEYS command blocks Redis -- use SCAN for production key iteration
- Expiry (TTL) is per key, not per hash field

## Related
- redis-caching-patterns
- redis-streams
- redis-pub-sub
