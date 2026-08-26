# cte-common-table-expressions

**Issue:** Using CTEs for readable, reusable query building blocks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Complex nested subqueries become unreadable; CTEs allow naming intermediate result sets.

## Pattern / Solution
```sql
-- Basic CTE
WITH active_users AS (
  SELECT id, email FROM users WHERE deleted_at IS NULL
),
recent_orders AS (
  SELECT customer_id, count(*) AS order_count
  FROM orders WHERE created_at > now() - interval ''30 days''
  GROUP BY customer_id
)
SELECT u.email, ro.order_count
FROM active_users u
LEFT JOIN recent_orders ro ON ro.customer_id = u.id;

-- Recursive CTE for hierarchical data
WITH RECURSIVE subordinates AS (
  SELECT id, manager_id, name FROM employees WHERE id = 1
  UNION ALL
  SELECT e.id, e.manager_id, e.name
  FROM employees e JOIN subordinates s ON e.manager_id = s.id
)
SELECT * FROM subordinates;
```

## Gotchas
- In PostgreSQL 12+, CTEs are inlined by default (not materialized); add `MATERIALIZED` to force isolation
- Recursive CTEs without a proper termination condition will loop infinitely
- Each CTE adds a planning unit; deeply chained CTEs can confuse the planner

## Related
- `subquery-vs-join.md`
- `window-functions-patterns.md`
