# explain-analyze-reading

**Issue:** Interpreting EXPLAIN ANALYZE output to diagnose slow queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A query is slow and you need to understand what the planner is actually doing.

## Pattern / Solution
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 10;

-- Key nodes to look for:
-- Seq Scan  → no index used; check if index needed
-- Index Scan → index used, heap fetched
-- Index Only Scan → best; no heap fetch
-- Hash Join / Merge Join / Nested Loop → join strategy
-- Sort → may spill to disk if "Sort Method: external merge"
-- Rows Removed by Filter: N → index used but row estimate off, run ANALYZE

-- Identify slow nodes: look for highest "actual time" values
```

## Gotchas
- `EXPLAIN` without `ANALYZE` shows estimates only — can be wildly wrong
- `BUFFERS` shows cache hits vs. disk reads — high `read` blocks = I/O bound
- Don''t run ANALYZE on production OLTP under heavy load; use `EXPLAIN (ANALYZE, TIMING OFF)` to reduce overhead

## Related
- `query-plan-optimization.md`
- `index-selectivity.md`
- `statistics-update-analyze.md`
