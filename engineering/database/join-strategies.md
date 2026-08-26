# join-strategies

**Issue:** Understanding nested loop, hash, and merge join strategies
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Choosing the wrong join method (or letting the planner choose badly) causes slow query execution.

## Pattern / Solution
```sql
-- Nested Loop: best for small outer set + index on inner
-- Hash Join: best for large unsorted tables, needs memory
-- Merge Join: best when both sides are pre-sorted on join key

-- Force hash join for testing
SET enable_nestloop = off;
EXPLAIN SELECT * FROM orders o JOIN customers c ON c.id = o.customer_id;

-- Ensure join columns are indexed
CREATE INDEX idx_orders_customer_id ON orders (customer_id);
CREATE INDEX idx_customers_id ON customers (id);  -- usually PK already

-- LATERAL join for row-level subqueries
SELECT u.id, recent.title
FROM users u,
LATERAL (
  SELECT title FROM posts WHERE user_id = u.id ORDER BY created_at DESC LIMIT 1
) recent;
```

## Gotchas
- Hash join requires work_mem; if spilling to disk, increase it: `SET work_mem = ''64MB''`
- Nested loop with no index on the inner side = O(n*m) — very slow
- Join column data types must match exactly or an implicit cast disables the index

## Related
- `lateral-joins.md`
- `explain-analyze-reading.md`
