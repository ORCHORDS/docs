# sql-query-explain-analyze

**Issue:** Query plan is suboptimal but the reason is unclear
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
EXPLAIN ANALYZE executes a query and returns the actual execution plan with row counts, execution times, and node costs.

## Pattern / Solution
1. Run: EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) SELECT ...\n2. Look for Seq Scan on large tables -- often indicates a missing index.\n3. Compare rows=estimated vs rows=actual -- large discrepancies indicate stale statistics.\n4. Run ANALYZE tablename to update statistics.\n5. Use pg_stat_user_tables to check last autoanalyze time.

## Gotchas
- EXPLAIN ANALYZE actually executes the query; wrap in a transaction and ROLLBACK for write queries.\n- Parallel workers appear in the plan; check max_parallel_workers_per_gather configuration.\n- pgsql-explain.depesz.com provides a visual plan viewer for PostgreSQL.

## Related
database-query-performance, index-strategy-performance, n-plus-one-detection
