# lateral-joins

**Issue:** Using LATERAL joins for row-by-row correlated subqueries with set-returning functions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Need to run a subquery that references the current row of the outer query — the correlated subquery equivalent but with JOIN semantics.

## Pattern / Solution
```sql
-- Latest post per user
SELECT u.id, u.email, p.title, p.created_at
FROM users u
LEFT JOIN LATERAL (
  SELECT title, created_at
  FROM posts
  WHERE user_id = u.id
  ORDER BY created_at DESC
  LIMIT 1
) p ON true;

-- Unnest with LATERAL
SELECT u.id, tag
FROM users u, LATERAL unnest(u.tags) AS tag;

-- Function returning set
SELECT u.id, f.*
FROM users u, LATERAL get_user_stats(u.id) f;
```

## Gotchas
- LATERAL is implicitly applied when a set-returning function appears in FROM
- `JOIN LATERAL ... ON true` is LEFT JOIN LATERAL semantics if you want rows without matches
- Can be slower than a window function for the same problem — benchmark both

## Related
- `join-strategies.md`
- `window-functions-patterns.md`
