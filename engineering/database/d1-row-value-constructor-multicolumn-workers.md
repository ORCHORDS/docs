# D1 Row Value Constructors and Multi-Column Comparisons in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Worker needs to filter or paginate by a composite key (e.g. `(user_id, created_at)`) or check membership across multiple columns at once, but the SQL becomes verbose and incorrect when written as independent `AND` / `OR` conditions. Row value constructors compress this into a single, semantically correct expression.

## Context
SQLite (and therefore D1) supports the SQL row value constructor syntax: `(col1, col2) operator (val1, val2)`. This allows compound comparisons on multiple columns in a single expression, which is essential for keyset pagination on composite keys, multi-column `IN` membership tests, and range scans that span two or more columns. Workers binds positional parameters (`?`) one-to-one with the constructor values.

---

## Row Value Constructor Syntax

A row value constructor is a parenthesized list of expressions treated as a tuple. It supports equality, ordering, and `IN` operators:

```sql
-- Equality: find a specific (user_id, session_id) pair
SELECT * FROM sessions
WHERE (user_id, session_id) = (42, 'abc-123');

-- Comparison: all sessions for user 42 after a given (user_id, created_at) cursor
SELECT * FROM events
WHERE (user_id, created_at, id) > (42, '2026-08-01T00:00:00Z', 9999)
ORDER BY user_id, created_at, id
LIMIT 50;

-- IN: membership across multiple columns
SELECT * FROM product_variants
WHERE (product_id, sku) IN (
  (10, 'RED-M'),
  (10, 'RED-L'),
  (11, 'BLUE-S')
);
```

---

## Keyset Pagination on Composite Keys

Offset-based pagination (`OFFSET n`) forces a full scan of the skipped rows. Keyset pagination is O(log N) when an index covers the sort columns. Row value constructors make the cursor condition correct for composite keys without the logical errors of separate `AND / OR` chains.

### The Problem with Naive Decomposition

```sql
-- INCORRECT: this is not equivalent to (user_id, created_at) > (42, '2026-08-01')
-- It filters WHERE user_id > 42 AND created_at > '2026-08-01',
-- which misses rows where user_id = 42 AND created_at > '2026-08-01'
SELECT * FROM events
WHERE user_id > 42
  AND created_at > '2026-08-01T00:00:00Z'
ORDER BY user_id, created_at
LIMIT 20;
```

```sql
-- CORRECT: row value constructor semantics
-- Returns all rows that come after (user_id=42, created_at='2026-08-01...')
-- in (user_id, created_at) sort order, including user_id=42 rows with later dates
SELECT * FROM events
WHERE (user_id, created_at) > (42, '2026-08-01T00:00:00Z')
ORDER BY user_id, created_at
LIMIT 20;
```

### Pagination in a Worker

```typescript
import type { Env } from './types';

interface EventRow {
  id: number;
  user_id: number;
  type: string;
  created_at: string;
}

interface Cursor {
  user_id: number;
  created_at: string;
  id: number;
}

function encodeCursor(row: EventRow): string {
  return btoa(JSON.stringify({ user_id: row.user_id, created_at: row.created_at, id: row.id }));
}

function decodeCursor(token: string): Cursor {
  return JSON.parse(atob(token)) as Cursor;
}

async function listEvents(
  db: D1Database,
  pageSize = 25,
  cursorToken?: string
): Promise<{ rows: EventRow[]; nextCursor: string | null }> {
  let stmt: D1PreparedStatement;

  if (cursorToken) {
    const cur = decodeCursor(cursorToken);
    // Three-column row value cursor: correct composite ordering
    stmt = db
      .prepare(
        `SELECT id, user_id, type, created_at
           FROM events
          WHERE (user_id, created_at, id) > (?, ?, ?)
          ORDER BY user_id ASC, created_at ASC, id ASC
          LIMIT ?`
      )
      .bind(cur.user_id, cur.created_at, cur.id, pageSize + 1);
  } else {
    stmt = db
      .prepare(
        `SELECT id, user_id, type, created_at
           FROM events
          ORDER BY user_id ASC, created_at ASC, id ASC
          LIMIT ?`
      )
      .bind(pageSize + 1);
  }

  const result = await stmt.all<EventRow>();
  const rows = result.results;
  const hasMore = rows.length > pageSize;
  const page = hasMore ? rows.slice(0, pageSize) : rows;
  const nextCursor = hasMore ? encodeCursor(page[page.length - 1]) : null;

  return { rows: page, nextCursor };
}
```

The composite index must match the ORDER BY direction to allow an index range scan:

```sql
CREATE INDEX IF NOT EXISTS idx_events_user_created_id
  ON events(user_id ASC, created_at ASC, id ASC);
```

---

## Multi-Column IN Membership

Row value constructors in `IN` clauses replace multiple `OR` conditions with a single, planner-friendly expression:

```sql
-- Check whether specific (product_id, warehouse_id) pairs are in stock
SELECT product_id, warehouse_id, qty
FROM inventory
WHERE (product_id, warehouse_id) IN (
  (101, 5),
  (101, 7),
  (202, 5)
);
```

### Dynamic Multi-Column IN in a Worker

```typescript
interface StockQuery {
  product_id: number;
  warehouse_id: number;
}

async function checkStock(db: D1Database, pairs: StockQuery[]): Promise<Map<string, number>> {
  if (pairs.length === 0) return new Map();

  // Build: (product_id, warehouse_id) IN ((?,?), (?,?), ...)
  const placeholders = pairs.map(() => '(?,?)').join(', ');
  const bindings = pairs.flatMap(p => [p.product_id, p.warehouse_id]);

  const result = await db
    .prepare(
      `SELECT product_id, warehouse_id, qty
         FROM inventory
        WHERE (product_id, warehouse_id) IN (${placeholders})`
    )
    .bind(...bindings)
    .all<{ product_id: number; warehouse_id: number; qty: number }>();

  const map = new Map<string, number>();
  for (const row of result.results) {
    map.set(`${row.product_id}:${row.warehouse_id}`, row.qty);
  }
  return map;
}
```

D1's maximum bind parameter count is 100. For larger sets, batch the pairs into groups:

```typescript
async function checkStockBatched(
  db: D1Database,
  pairs: StockQuery[]
): Promise<Map<string, number>> {
  const BATCH_SIZE = 45; // 45 pairs × 2 params = 90, under the 100-param limit
  const batches: StockQuery[][] = [];

  for (let i = 0; i < pairs.length; i += BATCH_SIZE) {
    batches.push(pairs.slice(i, i + BATCH_SIZE));
  }

  const allResults = await Promise.all(
    batches.map(batch => checkStock(db, batch))
  );

  const merged = new Map<string, number>();
  for (const m of allResults) {
    for (const [k, v] of m) merged.set(k, v);
  }
  return merged;
}
```

---

## Row Value Equality for Upsert Conflict Detection

Row value constructors work in `WHERE` clauses for targeted upsert lookups:

```sql
-- Check if a specific composite record exists before inserting
SELECT EXISTS (
  SELECT 1 FROM assignments
  WHERE (project_id, user_id, role) = (10, 42, 'reviewer')
) AS already_assigned;
```

```typescript
async function isAssigned(
  db: D1Database,
  projectId: number,
  userId: number,
  role: string
): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT EXISTS (
         SELECT 1 FROM assignments
         WHERE (project_id, user_id, role) = (?, ?, ?)
       ) AS already_assigned`
    )
    .bind(projectId, userId, role)
    .first<{ already_assigned: 0 | 1 }>();

  return row?.already_assigned === 1;
}
```

---

## Row Value Constructors in DELETE and UPDATE

```sql
-- Delete a batch of composite-keyed rows
DELETE FROM cart_items
WHERE (cart_id, item_id) IN (
  (55, 101),
  (55, 102),
  (56, 201)
);

-- Update a specific (user_id, device_id) pair
UPDATE push_tokens
SET token = 'new-token', updated_at = datetime('now')
WHERE (user_id, device_id) = (42, 'iphone-xyz');
```

---

## Anti-patterns

- **Decomposed AND conditions for tuple ordering** — `WHERE a > ? AND b > ?` is not the same as `WHERE (a, b) > (?, ?)`. The former is a rectangle in (a, b) space; the latter is a half-plane.
- **Unbounded multi-column IN with `flatMap` binds** — hitting D1's parameter limit silently fails with a binding error. Always cap batch size.
- **Using row value constructors on unindexed columns** — without a composite index matching the column order, the query falls back to a full table scan. Always verify with `EXPLAIN QUERY PLAN`.
- **Mixed ASC/DESC in a composite cursor** — row value constructor `>` applies a single lexicographic ordering (all columns ASC). If your `ORDER BY` mixes directions, the constructor does not produce a correct cursor; use explicit `OR` decomposition instead.

---

## Gotchas

- **SQLite version requirement** — row value constructor support in `IN` clauses requires SQLite ≥ 3.15.0 (released 2016). D1 uses a modern SQLite build and supports this, but local development with an older SQLite version may behave differently.
- **NULL in row value comparisons** — if any element of the row value constructor is NULL, the comparison result is NULL (unknown), which is falsy in a WHERE clause. Guard with `COALESCE` if cursor columns can be NULL.
- **`EXPLAIN QUERY PLAN` for constructor IN** — the planner may not always use the composite index for row value `IN` clauses in older SQLite optimizers. Check the plan and fall back to a `JOIN` against a VALUES clause if needed.
- **Parameter count limit** — D1 caps SQL parameters at 100 per statement. A multi-column IN over 50 pairs uses all 100 slots; leave headroom for other bound parameters in the same statement.

---

## Verification

```sql
-- Confirm row value > works correctly (should include (42, '2026-08-02') but not (43, '2026-07-01'))
CREATE TEMP TABLE t (a INTEGER, b TEXT);
INSERT INTO t VALUES (42, '2026-07-01'), (42, '2026-08-02'), (43, '2026-07-01');
SELECT * FROM t WHERE (a, b) > (42, '2026-08-01');
-- Expected: (42, '2026-08-02') and (43, '2026-07-01')

-- Confirm multi-column IN
SELECT * FROM t WHERE (a, b) IN ((42, '2026-07-01'), (43, '2026-07-01'));
-- Expected: both (42, '2026-07-01') and (43, '2026-07-01')

-- Confirm naive AND decomposition is NOT equivalent to row value >
SELECT * FROM t WHERE a > 42 AND b > '2026-08-01';
-- Expected: nothing (43 rows have b='2026-07-01' which fails b > '2026-08-01')
-- Contrast: row value > correctly returns (43, '2026-07-01')

-- Use EXPLAIN QUERY PLAN to verify index usage
EXPLAIN QUERY PLAN
SELECT * FROM events WHERE (user_id, created_at, id) > (42, '2026-08-01', 0)
ORDER BY user_id, created_at, id LIMIT 25;
-- Should show: SEARCH events USING INDEX idx_events_user_created_id
```

---

## Related

- `d1-pagination-cursor-keyset.md`
- `d1-covering-index-composite-key-workers.md`
- `d1-composite-index-design.md`
- `d1-exists-vs-in-subquery-performance.md`
- `d1-returning-clause-upsert-workers.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/rowvalue.html
- https://www.sqlite.org/lang_expr.html#in_operator
- https://www.sqlite.org/optoverview.html#row_values
