# statistics-update-analyze

**Issue:** Stale planner statistics cause poor query plans after bulk data changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
After bulk insert or delete, queries use wrong plan. EXPLAIN shows estimated rows wildly off from actual rows. Happens after ETL jobs or initial data loads.

## Pattern / Solution
Run ANALYZE table_name after bulk operations. Increase default_statistics_target for columns with skewed distribution. Check pg_stats view to see current statistics. Autoanalyze handles routine changes but not immediate post-bulk-load.

## Gotchas
- ANALYZE takes a share lock -- safe to run online but avoid during peak write periods
- Statistics are sampled; large tables may need default_statistics_target = 300+
- Extended statistics (CREATE STATISTICS) capture column correlations for multi-column predicates

## Related
- autovacuum-tuning
- explain-analyze-reading
- query-plan-optimization
