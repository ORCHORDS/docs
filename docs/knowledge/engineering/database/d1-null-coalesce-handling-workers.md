# D1 NULL Handling and COALESCE Patterns in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Queries return `null` where you expect a value, aggregates silently under-count,
JOIN conditions exclude rows you expected to match, or TypeScript types become
unexpectedly `T | null` throughout the codebase — all because SQL NULL
propagates in ways that differ from JavaScript `null` and `undefined`.

## Context

SQL NULL means "unknown" — it is not zero, not an empty string, not false.
Every comparison or arithmetic operation involving NULL yields NULL (not false,
not zero). Aggregates like `COUNT(col)`, `SUM`, `AVG` silently skip NULL rows.
D1 (SQLite) shares standard SQL NULL semantics. TypeScript workers receive NULL
values as JavaScript `null` from the D1 client.

Understanding NULL in D1 is critical for correct filtering, JOIN results,
aggregation, and schema design.

---

## NULL Comparisons: IS vs. =

```sql
-- Wrong: WHERE col = NULL is always false/NULL — never matches
SELECT * FROM users WHERE deleted_at = NULL;     -- returns 0 rows

-- Correct: IS NULL / IS NOT NULL
SELECT * FROM users WHERE deleted_at IS NULL;
SELECT * FROM users WHERE deleted_at IS NOT NULL;
```

```typescript
// Workers example: fetch non-deleted users
const { results } = await env.DB.prepare(`
  SELECT id, name FROM users
  WHERE deleted_at IS NULL
  ORDER BY created_at DESC
`).all<{ id: string; name: string }>();
```

SQLite also supports `IS` as a NULL-safe equality operator (equivalent to
`IS NOT DISTINCT FROM` in PostgreSQL):

```sql
-- True when both sides are NULL or both are equal
SELECT 1 WHERE NULL IS NULL;          -- returns 1
SELECT 1 WHERE NULL = NULL;           -- returns nothing (NULL result)
```

---

## COALESCE — First Non-NULL Value

`COALESCE(expr1, expr2, ..., exprN)` returns the first non-NULL argument.
Use it to supply defaults when a column may be NULL.

```typescript
interface UserProfile {
  id: string;
  display_name: string;  // never null after COALESCE
  avatar_url: string;
  bio: string;
}

const { results } = await env.DB.prepare(`
  SELECT
    id,
    COALESCE(display_name, username, 'Anonymous')  AS display_name,
    COALESCE(avatar_url, '/img/default-avatar.png') AS avatar_url,
    COALESCE(bio, '')                               AS bio
  FROM users
  WHERE id = ?
`).bind(userId).all<UserProfile>();
```

In TypeScript this keeps `UserProfile` free of `| null` union types,
provided the final `COALESCE` argument is a non-NULL literal.

---

## NULLIF — Produce NULL Conditionally

`NULLIF(expr1, expr2)` returns NULL when `expr1 = expr2`, otherwise returns
`expr1`. Useful for treating sentinel values (empty string, zero) as NULL.

```typescript
// Treat empty string bio as NULL for aggregation / display
const { results } = await env.DB.prepare(`
  SELECT
    id,
    NULLIF(bio, '')           AS bio,          -- NULL if empty
    NULLIF(promo_code, 'NONE') AS promo_code   -- NULL if sentinel
  FROM users
`).all<{ id: string; bio: string | null; promo_code: string | null }>();
```

Combine `NULLIF` with `COALESCE` to collapse sentinels into defaults:

```sql
COALESCE(NULLIF(promo_code, 'NONE'), 'NO_PROMO')
```

---

## Aggregates and NULL

Standard aggregates (`SUM`, `AVG`, `MAX`, `MIN`, `COUNT(col)`) silently
ignore NULL values. `COUNT(*)` counts all rows including those with NULLs.

```typescript
// Wrong: AVG ignores NULL rows → result skewed toward non-null rows only
const stats = await env.DB.prepare(`
  SELECT AVG(response_time_ms) AS avg_ms FROM requests
`).first<{ avg_ms: number | null }>();

// Correct when NULL means "no response" (treat as 0):
const statsFixed = await env.DB.prepare(`
  SELECT AVG(COALESCE(response_time_ms, 0)) AS avg_ms FROM requests
`).first<{ avg_ms: number }>();

// COUNT rows where a column IS NULL (missing data report):
const missing = await env.DB.prepare(`
  SELECT
    COUNT(*)              AS total_rows,
    COUNT(email)          AS rows_with_email,
    COUNT(*) - COUNT(email) AS rows_missing_email
  FROM users
`).first<{ total_rows: number; rows_with_email: number; rows_missing_email: number }>();
```

---

## NULL in JOINs

NULL values in JOIN columns cause rows to drop silently:

```sql
-- If orders.user_id IS NULL, this row will NOT appear in the INNER JOIN result
SELECT u.name, o.total
FROM users u
INNER JOIN orders o ON o.user_id = u.id;

-- Use LEFT JOIN to keep users with no orders
SELECT u.name, COALESCE(o.total, 0) AS total
FROM users u
LEFT JOIN orders o ON o.user_id = u.id;
```

```typescript
const { results } = await env.DB.prepare(`
  SELECT
    u.id,
    u.name,
    COUNT(o.id)           AS order_count,
    COALESCE(SUM(o.total), 0) AS lifetime_value
  FROM users u
  LEFT JOIN orders o ON o.user_id = u.id
  GROUP BY u.id, u.name
`).all<{ id: string; name: string; order_count: number; lifetime_value: number }>();
```

---

## NULL in UNIQUE Constraints

SQLite treats each NULL as distinct in UNIQUE constraints — multiple rows with
NULL in a UNIQUE column do not conflict with each other (standard SQL
behaviour). If you need "at most one NULL per group", use a partial index:

```sql
-- At most one active subscription per user (NULL = inactive, not counted)
-- Allow multiple inactive rows but only one active per user:
CREATE UNIQUE INDEX ux_one_active_sub_per_user
  ON subscriptions (user_id)
  WHERE status = 'active';
```

---

## NULL in ORDER BY

SQLite places NULL values **last** in ascending order and **first** in
descending order. PostgreSQL has `NULLS FIRST / NULLS LAST`; SQLite does not.
Work around it with `COALESCE` or a sort key:

```typescript
// Sort users: those with a last_login come first (most recent first),
// then users who have never logged in at the end
const { results } = await env.DB.prepare(`
  SELECT id, name, last_login
  FROM users
  ORDER BY
    CASE WHEN last_login IS NULL THEN 1 ELSE 0 END ASC,
    last_login DESC
`).all<{ id: string; name: string; last_login: string | null }>();
```

---

## TypeScript: Narrowing D1 NULL Returns

D1's `first<T>()` and `all<T>()` return fields as their TypeScript type. Mark
nullable D1 columns with `| null` in your result type to avoid runtime errors:

```typescript
interface Order {
  id: string;
  total: number;
  refunded_at: string | null;   // nullable in DB
  notes: string | null;
}

function formatOrder(order: Order): string {
  const refund = order.refunded_at
    ? `Refunded on ${order.refunded_at}`
    : "Not refunded";
  const notes = order.notes ?? "No notes";
  return `${refund} — ${notes}`;
}
```

Use `COALESCE` in SQL to push null-elimination to the database layer and keep
TypeScript types non-nullable wherever possible.

---

## Anti-patterns

- **`WHERE col != 'value'`**: excludes rows where `col IS NULL` because
  `NULL != 'value'` evaluates to NULL (falsy). Add `OR col IS NULL` if you
  intend to include nulls.
- **`COALESCE` in an indexed column's WHERE clause**: `WHERE COALESCE(col, 0) > 5`
  defeats a plain B-tree index on `col`. Rewrite as
  `WHERE col > 5 OR (col IS NULL AND 0 > 5)` or create an expression index.
- **Trusting `COUNT(*)` to count non-null values**: use `COUNT(column)`.
- **Comparing to NULL with `=` in TypeScript-assembled SQL**: always use
  parameterized queries with `IS NULL` / `IS NOT NULL` predicates.

---

## Gotchas

- D1 returns SQL NULL as JavaScript `null`, not `undefined`. Use `?? default`
  (nullish coalescing) not `|| default` (falsy check) to handle it — `0` and
  `""` are falsy in JS but valid non-NULL SQL values.
- `first<T>()` returns `null` (not throws) when no row matches. Distinguish
  "row not found" (`null` from `first()`) from "column is NULL" (a `null`
  field on a returned row).
- SQLite `IFNULL(a, b)` is an alias for `COALESCE(a, b)` with exactly two
  arguments — use `COALESCE` for portability and multi-argument cases.
- Adding a `NOT NULL` constraint to an existing column requires a table rebuild
  in SQLite (no `ALTER TABLE … ALTER COLUMN` support).

---

## Verification

```typescript
// Confirm NULL IS NULL semantics
const test = await env.DB.prepare(
  "SELECT (NULL IS NULL) AS is_null_check, (NULL = NULL) AS eq_check"
).first<{ is_null_check: number; eq_check: number | null }>();
console.assert(test?.is_null_check === 1,  "IS NULL should return 1");
console.assert(test?.eq_check     === null, "= NULL should return NULL");

// Confirm COALESCE returns default
const coalesce = await env.DB.prepare(
  "SELECT COALESCE(NULL, NULL, 42) AS val"
).first<{ val: number }>();
console.assert(coalesce?.val === 42, "COALESCE should return 42");
```

---

## Related

- `d1-check-constraint-domain-validation-workers.md`
- `d1-strict-tables-type-enforcement-workers.md`
- `d1-column-affinity-type-coercion-workers.md`
- `d1-soft-delete-workers-middleware.md`
- `d1-partial-index-filtered-queries-workers.md`

---

## Sources

- SQLite NULL handling: https://www.sqlite.org/nulls.html
- SQLite COALESCE / NULLIF: https://www.sqlite.org/lang_corefunc.html
- SQL NULL semantics (ISO standard summary): https://en.wikipedia.org/wiki/Null_(SQL)
- Cloudflare D1 Worker API: https://developers.cloudflare.com/d1/worker-api/
