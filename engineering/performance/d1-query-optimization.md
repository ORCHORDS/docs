# d1-query-optimization

**Issue:** D1 SQLite queries are slow in production Workers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare D1 is a serverless SQLite database running at Cloudflare's edge. Queries must be fast (< 10ms CPU time) due to Worker CPU limits.

## Pattern / Solution
1. Add indexes on all WHERE clause columns.\n2. Use prepared statements: env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(id).first().\n3. Batch multiple queries with env.DB.batch([stmt1, stmt2]) to reduce round trips.\n4. Use EXPLAIN QUERY PLAN in local development to verify index usage.\n5. Keep result sets small; use LIMIT aggressively.

## Gotchas
- D1 is read-consistent at the primary but reads from replicas may be slightly stale.\n- SQLite's TEXT type affinity can cause unexpected implicit conversions in comparisons.\n- D1 does not support all PostgreSQL features; test your SQL dialect differences.

## Related
cloudflare-workers-performance, workers-cpu-profiling, database-query-performance, index-strategy-performance
