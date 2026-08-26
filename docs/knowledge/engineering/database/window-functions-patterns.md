# window-functions-patterns

**Issue:** Using window functions for rankings, running totals, and lag/lead analysis
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GROUP BY collapses rows; window functions allow aggregation while keeping all rows visible.

## Pattern / Solution
```sql
-- Row number per partition
SELECT id, customer_id, amount,
       row_number() OVER (PARTITION BY customer_id ORDER BY created_at DESC) AS rn
FROM orders;

-- Running total
SELECT id, amount,
       sum(amount) OVER (ORDER BY created_at) AS running_total
FROM orders;

-- Lag/lead for period-over-period comparisons
SELECT month, revenue,
       lag(revenue) OVER (ORDER BY month) AS prev_month,
       revenue - lag(revenue) OVER (ORDER BY month) AS delta
FROM monthly_revenue;

-- Top N per group (filter after window)
SELECT * FROM (
  SELECT *, row_number() OVER (PARTITION BY customer_id ORDER BY amount DESC) AS rn
  FROM orders
) t WHERE rn <= 3;
```

## Gotchas
- Window functions execute after WHERE/GROUP BY/HAVING but before ORDER BY and LIMIT
- Cannot use window functions directly in WHERE — wrap in a subquery or CTE
- PARTITION BY with many distinct values can be memory-intensive

## Related
- `cte-common-table-expressions.md`
- `lateral-joins.md`
