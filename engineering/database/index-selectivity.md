# index-selectivity

**Issue:** Understanding why low-selectivity indexes are ignored by the planner
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An index exists but the query planner does a sequential scan anyway — the column has too few distinct values.

## Pattern / Solution
```sql
-- Check selectivity
SELECT attname,
       n_distinct,
       correlation
FROM pg_stats
WHERE tablename = ''orders'' AND attname = ''status'';

-- n_distinct close to 1 or 2 = very low selectivity = index rarely useful
-- n_distinct = -1 means unique; high selectivity

-- Force planner to consider index (for testing only)
SET enable_seqscan = off;
EXPLAIN SELECT * FROM orders WHERE status = ''pending'';

-- Improve selectivity with a partial index
CREATE INDEX idx_orders_pending ON orders (created_at) WHERE status = ''pending'';
```

## Gotchas
- The planner estimates that a full scan is cheaper when selectivity < ~5%
- After bulk loads, run ANALYZE to update statistics
- Correlation close to 1 means physically ordered — good for range scans

## Related
- `partial-indexes.md`
- `explain-analyze-reading.md`
- `statistics-update-analyze.md`
