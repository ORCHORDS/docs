# D1 UNION, INTERSECT, and EXCEPT Set Operations in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Worker needs to combine rows from multiple queries — merging result sets from different tables, finding the overlap between two result sets, or subtracting one result set from another — without fetching all rows into JavaScript and doing the merge there.

## Context
D1 (SQLite) supports all three SQL set operators: `UNION`, `INTERSECT`, and `EXCEPT`. Each operates on the columns of two or more `SELECT` statements and returns a single result set. Set operations reduce round-trips and push combination logic into the database engine, which can leverage query-planner optimizations (sort-merge, hash deduplication) unavailable in JavaScript-land.

---

## UNION: Merge Result Sets

`UNION` returns all rows from both queries, removing duplicates. `UNION ALL` retains duplicates and is always faster because it skips the deduplication sort.

```sql
-- Combine active users from two tenants into one result set
SELECT user_id, name, 'tenant_a' AS source FROM tenant_a_users WHERE active = 1
UNION ALL
SELECT user_id, name, 'tenant_b' AS source FROM tenant_b_users WHERE active = 1;
```

Rules:
- Both sides must have the same number of columns.
- Column types need not match exactly — SQLite uses type affinity coercion.
- Column names in the result come from the **first** `SELECT`.
- `ORDER BY` and `LIMIT` apply to the final combined result, not to individual branches.

```sql
-- UNION (with deduplication) vs UNION ALL
-- Use UNION only when you genuinely need to collapse duplicates
SELECT email FROM newsletter_subscribers
UNION
SELECT email FROM transactional_subscribers
ORDER BY email;

-- UNION ALL is ~2× faster on large sets; prefer it when duplicates are impossible
SELECT email FROM list_a
UNION ALL
SELECT email FROM list_b;
```

### UNION in a Worker

```typescript
interface UserRow {
  user_id: number;
  name: string;
  source: string;
}

async function getMergedUsers(db: D1Database): Promise<UserRow[]> {
  const result = await db
    .prepare(
      `SELECT user_id, name, 'active'   AS source FROM users  WHERE status = 'active'
       UNION ALL
       SELECT user_id, name, 'archived' AS source FROM archive WHERE migrated = 1
       ORDER BY name ASC
       LIMIT 500`
    )
    .all<UserRow>();

  return result.results;
}
```

---

## INTERSECT: Rows Common to Both Queries

`INTERSECT` returns only rows that appear in **both** result sets (with implicit deduplication). There is no `INTERSECT ALL` in SQLite.

```sql
-- Users who are both email subscribers AND have made a purchase
SELECT user_id FROM email_subscribers
INTERSECT
SELECT user_id FROM orders
ORDER BY user_id;
```

`INTERSECT` is equivalent to a semi-join and the query planner may rewrite it as one. An index on the key column used in both branches improves performance:

```sql
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_email_subs_user_id ON email_subscribers(user_id);
```

### INTERSECT vs INNER JOIN

`INTERSECT` is concise for checking set membership without pulling in extra columns. Use a `JOIN` when you need columns from both tables:

```sql
-- INTERSECT: just the user IDs in common
SELECT user_id FROM subscribers
INTERSECT
SELECT user_id FROM premium_members;

-- JOIN: user details from both tables
SELECT s.user_id, s.name, p.plan
FROM subscribers s
JOIN premium_members p ON s.user_id = p.user_id;
```

### INTERSECT in a Worker

```typescript
interface UserIdRow {
  user_id: number;
}

async function getPremiumSubscribers(db: D1Database): Promise<number[]> {
  const result = await db
    .prepare(
      `SELECT user_id FROM newsletter_subscribers
       INTERSECT
       SELECT user_id FROM premium_members
       ORDER BY user_id`
    )
    .all<UserIdRow>();

  return result.results.map(r => r.user_id);
}
```

---

## EXCEPT: Rows in the First Set But Not the Second

`EXCEPT` returns rows from the first query that do not appear in the second (also called `MINUS` in some databases). SQLite supports `EXCEPT` only.

```sql
-- Users who subscribed but never purchased
SELECT user_id FROM subscribers
EXCEPT
SELECT user_id FROM orders;

-- Find deprecated feature flags still referenced in active configs
SELECT flag_name FROM deprecated_flags
EXCEPT
SELECT DISTINCT flag_name FROM feature_config WHERE active = 1;
```

### EXCEPT for Soft-Delete Reconciliation

```sql
-- IDs present in the source table but missing from the replica
SELECT id FROM source_table
EXCEPT
SELECT id FROM replica_table
ORDER BY id;
```

### EXCEPT in a Worker

```typescript
async function getUnconvertedLeads(db: D1Database): Promise<number[]> {
  const result = await db
    .prepare(
      `SELECT lead_id FROM leads
       EXCEPT
       SELECT lead_id FROM conversions
       ORDER BY lead_id
       LIMIT 100`
    )
    .all<{ lead_id: number }>();

  return result.results.map(r => r.lead_id);
}
```

---

## Composing Set Operations with CTEs

Set operations combine cleanly with Common Table Expressions for readability:

```sql
WITH
  newsletter AS (SELECT user_id FROM email_subscribers WHERE active = 1),
  purchasers AS (SELECT DISTINCT user_id FROM orders WHERE total_cents > 0),
  high_value  AS (SELECT user_id FROM users WHERE lifetime_value_cents > 50000)

-- Users who bought something but are not yet email subscribers
SELECT user_id FROM purchasers
EXCEPT
SELECT user_id FROM newsletter

INTERSECT   -- and who are high-value
SELECT user_id FROM high_value

ORDER BY user_id;
```

---

## Ordering and Limiting Combined Results

`ORDER BY` after a set operation sorts the final result. Clauses inside individual branches are not allowed in standard SQLite and will error:

```sql
-- INVALID: ORDER BY inside a branch
SELECT id FROM a ORDER BY id    -- syntax error when combined with UNION
UNION ALL
SELECT id FROM b;

-- VALID: ORDER BY on the compound result
SELECT id FROM a
UNION ALL
SELECT id FROM b
ORDER BY id;

-- Per-branch ordering requires a wrapping subquery
SELECT * FROM (SELECT id, 1 AS branch_order FROM a ORDER BY id LIMIT 10)
UNION ALL
SELECT * FROM (SELECT id, 2 AS branch_order FROM b ORDER BY id LIMIT 10)
ORDER BY branch_order, id;
```

---

## Performance Notes

- `UNION ALL` is always faster than `UNION` — use `UNION` only when you need deduplication.
- `INTERSECT` and `EXCEPT` sort both sides before comparing; ensure columns used in the comparison are indexed.
- Very large set operations can hit D1's 1 MB response size limit on the combined result; add `LIMIT` clauses or paginate with cursor keys.
- When both branches of a `UNION ALL` scan the same table with different `WHERE` clauses, consider a single scan with `CASE` or `FILTER` instead: `SELECT id, SUM(CASE WHEN status='a' THEN 1 END), SUM(CASE WHEN status='b' THEN 1 END) FROM t`.

---

## Anti-patterns

- **Mismatched column counts** — SQLite raises an error; always count columns in each branch before combining.
- **Using `UNION` when `UNION ALL` is correct** — the deduplication sort on large sets is expensive and silent; if duplicates are structurally impossible, always use `UNION ALL`.
- **Relying on column names from the second branch** — the result set takes column names from the first `SELECT`. Aliasing in the second branch is silently ignored.
- **Applying `ORDER BY` to individual branches** — SQLite accepts this only for subqueries; at the top level it is a syntax error.

---

## Gotchas

- **NULL handling in INTERSECT / EXCEPT** — SQLite treats two NULLs as equal for the purposes of set deduplication (unlike `=` comparisons). A `NULL` in the first set will match a `NULL` in the second set in `INTERSECT`.
- **EXCEPT is not symmetric** — `A EXCEPT B` and `B EXCEPT A` produce different results. Order matters.
- **Type coercion across branches** — if one branch returns `INTEGER` and another returns `TEXT` for the same column position, SQLite coerces based on affinity and comparison rules. Explicit `CAST` makes intent clear.
- **D1 response size limit** — the combined result of a set operation counts toward D1's per-query 1 MB result limit. Large `UNION ALL` across two big tables can hit this unexpectedly.

---

## Verification

```sql
-- Verify UNION ALL preserves duplicates; UNION deduplicates
SELECT 1 AS n UNION ALL SELECT 1;   -- returns two rows: 1, 1
SELECT 1 AS n UNION     SELECT 1;   -- returns one row:  1

-- Verify INTERSECT finds only common rows
SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3
  INTERSECT
SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4;
-- Should return: 2, 3

-- Verify EXCEPT removes matching rows
SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3
  EXCEPT
SELECT 2 UNION ALL SELECT 4;
-- Should return: 1, 3

-- NULL equality in set ops
SELECT NULL INTERSECT SELECT NULL;
-- Returns one row (NULL), unlike NULL = NULL which is false
```

---

## Related

- `d1-aggregate-filter-pivot-analytics-workers.md`
- `d1-window-functions-analytics.md`
- `d1-recursive-cte-hierarchical-data-workers.md`
- `cte-common-table-expressions.md`
- `d1-exists-vs-in-subquery-performance.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/lang_select.html#compound_select_statements
- https://www.sqlite.org/optoverview.html
