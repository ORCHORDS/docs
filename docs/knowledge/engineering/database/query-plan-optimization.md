# query-plan-optimization

**Issue:** Techniques to guide the query planner toward better execution plans
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The planner picks a bad join order or ignores a useful index due to stale statistics or unusual data distributions.

## Pattern / Solution
```sql
-- Update statistics on specific table
ANALYZE orders;

-- Increase statistics target for skewed columns
ALTER TABLE orders ALTER COLUMN status SET STATISTICS 500;

-- Use CTEs to force materialization (PG12+ CTEs are inlined by default)
WITH pending AS MATERIALIZED (
  SELECT * FROM orders WHERE status = ''pending''
)
SELECT * FROM pending WHERE amount > 1000;

-- Avoid functions on indexed columns in WHERE
-- Bad:  WHERE date_trunc(''day'', created_at) = ''2026-01-01''
-- Good: WHERE created_at >= ''2026-01-01'' AND created_at < ''2026-01-02''
```

## Gotchas
- `SET enable_hashjoin = off` is a sledgehammer — use only to test, never in production permanently
- Planner hints are not native to Postgres; use `pg_hint_plan` extension if you need them
- After adding indexes, statistics need refresh via ANALYZE before planner uses them

## Related
- `explain-analyze-reading.md`
- `index-selectivity.md`
