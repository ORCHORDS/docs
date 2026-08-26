# subquery-vs-join

**Issue:** When to use subqueries vs. JOINs for clarity and performance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Subqueries can be more readable but correlated subqueries run once per row — a hidden N+1.

## Pattern / Solution
```sql
-- Correlated subquery (bad for large sets — runs per row)
SELECT id FROM orders o
WHERE (SELECT email FROM customers WHERE id = o.customer_id) LIKE ''%@example.com'';

-- Equivalent JOIN (better)
SELECT o.id FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.email LIKE ''%@example.com'';

-- Subquery fine for one-time aggregation
SELECT * FROM orders
WHERE amount > (SELECT avg(amount) FROM orders);

-- EXISTS often faster than IN for large sets
SELECT * FROM orders o
WHERE EXISTS (SELECT 1 FROM customers c WHERE c.id = o.customer_id AND c.active);
```

## Gotchas
- `IN (subquery)` can be slow if the subquery returns NULLs — use EXISTS instead
- Modern PostgreSQL often rewrites correlated subqueries to joins automatically
- CTEs are sometimes clearer than nested subqueries with no performance difference

## Related
- `cte-common-table-expressions.md`
- `join-strategies.md`
