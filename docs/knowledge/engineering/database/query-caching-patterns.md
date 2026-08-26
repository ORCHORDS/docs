# query-caching-patterns

**Issue:** Expensive queries run repeatedly without caching, wasting database resources
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dashboard queries hitting the database on every page load. Read-heavy endpoints with high latency despite indexes. Same aggregation computed thousands of times per minute.

## Pattern / Solution
Layer caching by query type: materialized views for complex aggregations refreshed on schedule; Redis for short-lived result sets with TTL; application-level memoization for request-scoped queries; Postgres query result caching via pg_query_cache extension. Cache key must encode all query parameters. Invalidate on data change via CDC or explicit purge.

## Gotchas
- Stale cache more dangerous than slow query for financial data -- choose TTL carefully
- Cache key collision invalidates unrelated data -- namespace keys by entity type
- Cached NULL results need explicit handling; most cache clients do not distinguish miss from cached null

## Related
- redis-caching-patterns
- read-replicas-routing
- cqrs-read-write-split
