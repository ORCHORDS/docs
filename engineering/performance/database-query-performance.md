# database-query-performance

**Issue:** Slow queries cause high response latency
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Database queries are often the dominant factor in API response time. Slow queries result from missing indexes, full table scans, inefficient joins, or large result sets.

## Pattern / Solution
1. Identify slow queries via slow query log or pg_stat_statements.\n2. Use EXPLAIN ANALYZE to see query execution plans.\n3. Add indexes on columns used in WHERE, JOIN ON, and ORDER BY clauses.\n4. Use SELECT with specific column names; avoid SELECT *.\n5. Paginate large result sets with LIMIT/OFFSET or cursor-based pagination.

## Gotchas
- EXPLAIN shows the plan the optimizer chose; EXPLAIN ANALYZE shows actual vs. estimated row counts.\n- Indexes have write overhead; don't index every column.\n- pg_stat_statements must be preloaded: shared_preload_libraries = 'pg_stat_statements'.

## Related
sql-query-explain-analyze, index-strategy-performance, n-plus-one-detection, connection-pool-sizing
