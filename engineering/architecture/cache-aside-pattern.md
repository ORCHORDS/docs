# cache-aside-pattern

**Issue:** Repeated reads of the same data saturate the database
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A product detail page causes thousands of identical database queries per minute because no caching layer exists.

## Pattern / Solution
Application checks the cache first. On a miss, reads from the database, populates the cache, and returns the value. On a hit, returns the cached value directly. The application manages cache population and invalidation explicitly.

## Gotchas
Cache stampede occurs when many concurrent requests all miss and query the database simultaneously. Use a lock or probabilistic early expiration to mitigate. Cache keys must be deterministic and scoped correctly to avoid data leakage between users.

## Related
cache-stampede-prevention, read-through-cache, write-through-cache, distributed-caching
