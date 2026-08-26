# distributed-caching

**Issue:** Local in-process caches do not share state across multiple application instances
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A horizontally scaled API has 20 instances each with their own local cache. A cache invalidation only affects one instance.

## Pattern / Solution
Use a shared cache cluster such as Redis or Memcached accessible to all application instances. Implement a cache invalidation bus (pub/sub) for active invalidation. Consider a two-tier cache: local L1 for hot keys and shared L2 for the full key space.

## Gotchas
Network round-trips to a remote cache add latency. For sub-millisecond requirements, L1 local cache is necessary. Cache cluster availability becomes a dependency; circuit break around cache calls.

## Related
cache-aside-pattern, cache-stampede-prevention, service-discovery-patterns
