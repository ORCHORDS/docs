# Composite Index Design for D1 Query Optimization

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

D1 queries are performing full-table scans as usage grows, visible through slow response times and high `rows_read` counts in Wrangler analytics. You need to design composite indexes that cover the common access patterns — user-scoped recent-item lists, soft-delete filtering, and JSON-column lookups — without over-indexing and slowing down writes.

---

## Context

SQLite (and D1) uses a B-tree index for every non-virtual index. Composite indexes are effective when the leftmost columns of the index match the `WHERE` and `ORDER BY` clauses of a query — this is the "leftmost prefix rule". A covering index includes all columns referenced in `SELECT`, `WHERE`, and `ORDER BY`, letting SQLite satisfy the query entirely from the index without touching the main table. Partial indexes (`WHERE deleted_at IS NULL`) reduce index size for soft-delete patterns. Generated columns allow indexing an expression like a JSON field without storing a redundant column in the app layer. `EXPLAIN QUERY PLAN` in D1 reveals whether SQLite uses a scan, index scan, or covering index scan.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS items (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT    NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'active', -- 'active' | 'archived' | 'deleted'
  title       TEXT    NOT NULL,
  metadata    TEXT,                               -- JSON blob
  deleted_at  TEXT,                               -- NULL = not deleted (soft-delete)
  created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------------------
-- INDEX 1: Composite covering index for "my recent items" query pattern.
-- Query: SELECT id, title, status, created_at FROM items
--        WHERE user_id = ? AND deleted_at IS NULL
--        ORDER BY created_at DESC LIMIT 20;
--
-- Column order rationale:
--   1. user_id     — equality filter, highest cardinality reduction
--   2. created_at  — ORDER BY column; DESC matches typical feed order
--   3. status      — included for WHERE / SELECT without table lookup
-- -----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_items_user_created_status
  ON items(user_id, created_at DESC, status);

-- -----------------------------------------------------------------------
-- INDEX 2: Partial index — only indexes non-deleted rows.
-- Dramatically smaller than a full index when soft-deleted rows accumulate.
-- Covers: WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC
-- -----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_items_active
  ON items(user_id, created_at DESC)
  WHERE deleted_at IS NULL;

-- -----------------------------------------------------------------------
-- INDEX 3: Generated column index for JSON field extraction.
-- Avoids json_extract() in WHERE clauses, which bypasses indexes.
-- -----------------------------------------------------------------------
ALTER TABLE items ADD COLUMN meta_category TEXT
  GENERATED ALWAYS AS (json_extract(metadata, '$.category')) VIRTUAL;

CREATE INDEX IF NOT EXISTS idx_items_meta_category
  ON items(user_id, meta_category);

-- -----------------------------------------------------------------------
-- STATUS index for admin dashboard queries across all users
-- -----------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_items_status_created
  ON items(status, created_at DESC);
```

---

## Section 2 — Worker implementation

```typescript
// src/db/items.ts
import { Env } from '../types';

interface Item {
  id: number;
  title: string;
  status: string;
  created_at: string;
}

interface ItemQueryOptions {
  limit?: number;
  before?: string;  // created_at cursor for keyset pagination
  status?: string;
  category?: string;
}

/**
 * Fetch the authenticated user's recent active items.
 * Uses idx_items_active (partial) or idx_items_user_created_status.
 */
export async function listUserItems(
  env: Env,
  userId: string,
  opts: ItemQueryOptions = {}
): Promise<Item[]> {
  const limit = Math.min(opts.limit ?? 20, 100);
  const bindings: unknown[] = [userId];

  let sql = `
    SELECT id, title, status, created_at
    FROM items
    WHERE user_id = ?
      AND deleted_at IS NULL
  `;

  if (opts.status) {
    sql += ' AND status = ?';
    bindings.push(opts.status);
  }

  if (opts.category) {
    // Uses the generated column index idx_items_meta_category
    sql += ' AND meta_category = ?';
    bindings.push(opts.category);
  }

  // Keyset pagination: skip rows older than the cursor
  if (opts.before) {
    sql += ' AND created_at < ?';
    bindings.push(opts.before);
  }

  sql += ' ORDER BY created_at DESC LIMIT ?';
  bindings.push(limit);

  const { results } = await env.DB.prepare(sql)
    .bind(...bindings)
    .all<Item>();

  return results ?? [];
}

/**
 * Run EXPLAIN QUERY PLAN and return the plan as a string.
 * Use this in a dev-only endpoint to verify index usage.
 */
export async function explainQueryPlan(
  env: Env,
  sql: string,
  bindings: unknown[]
): Promise<string> {
  const { results } = await env.DB.prepare(
    `EXPLAIN QUERY PLAN ${sql}`
  )
    .bind(...bindings)
    .all<{ detail: string }>();

  return (results ?? []).map((r) => r.detail).join('\n');
}

// Dev-only route: GET /dev/query-plan?sql=...
export async function handleQueryPlan(
  request: Request,
  env: Env
): Promise<Response> {
  if (env.ENVIRONMENT !== 'development') {
    return Response.json({ error: 'Forbidden' }, { status: 403 });
  }

  const url = new URL(request.url);
  const sql = url.searchParams.get('sql') ?? '';

  if (!sql) {
    return Response.json({ error: 'sql param required' }, { status: 400 });
  }

  const plan = await explainQueryPlan(env, sql, []);
  return Response.json({ plan });
}
```

---

## Section 3 — Query / Migration helper

```sql
-- Run these EXPLAIN QUERY PLAN checks to validate index usage.
-- Look for "USING INDEX" or "USING COVERING INDEX" in the output.
-- "SCAN" without an index name = full table scan = add or fix an index.

-- Should use idx_items_active (partial index)
EXPLAIN QUERY PLAN
SELECT id, title, status, created_at
FROM items
WHERE user_id = 'u1'
  AND deleted_at IS NULL
ORDER BY created_at DESC
LIMIT 20;

-- Should use idx_items_meta_category
EXPLAIN QUERY PLAN
SELECT id, title
FROM items
WHERE user_id = 'u1'
  AND meta_category = 'music'
  AND deleted_at IS NULL;

-- Should use idx_items_status_created for admin queries
EXPLAIN QUERY PLAN
SELECT id, user_id, title, created_at
FROM items
WHERE status = 'active'
ORDER BY created_at DESC
LIMIT 50;

-- Check all indexes on the items table
SELECT name, sql FROM sqlite_master
WHERE type = 'index' AND tbl_name = 'items'
ORDER BY name;

-- Count index usage stats (SQLite 3.31+, available in D1)
SELECT * FROM sqlite_stat1 WHERE tbl = 'items';
```

---

## Anti-patterns

- **Indexing individual columns separately instead of compositely** — Three single-column indexes on `(user_id)`, `(created_at)`, `(status)` cannot satisfy a multi-column `WHERE user_id = ? AND status = ?` query as efficiently as one composite index.
- **Putting low-cardinality columns first** — `CREATE INDEX ON items(status, user_id)` where `status` has only 3 values forces SQLite to scan a large portion of the index. Put the highest-cardinality equality column first.
- **Using `json_extract()` in `WHERE` without a generated column** — `WHERE json_extract(metadata, '$.category') = 'music'` performs a full scan regardless of any index. Create a generated column and index that instead.
- **Over-indexing write-heavy tables** — Each index adds overhead to `INSERT`/`UPDATE`/`DELETE`. Audit indexes with `sqlite_stat1` and drop any that no query uses.
- **Ignoring `DESC` in composite indexes** — `ORDER BY created_at DESC` benefits from an index defined with `DESC`; a `DESC` sort against an `ASC` index forces a reverse scan which may still be fast but is not optimal for range queries.

---

## Gotchas

- Partial indexes (`WHERE deleted_at IS NULL`) are only used by the query planner when the query's `WHERE` clause literally includes `deleted_at IS NULL` — a query using `deleted_at = ''` will not match.
- Generated columns marked `VIRTUAL` are computed on read and not stored; `STORED` generated columns occupy space but allow the value to be used in indexes without recomputing. D1 supports both.
- `EXPLAIN QUERY PLAN` output in D1 differs slightly from local SQLite because D1 uses a newer SQLite build; always verify on the remote database.
- `sqlite_stat1` is only populated after `ANALYZE` is run. D1 runs `ANALYZE` automatically, but freshly created tables may show no stats until they contain data.
- Composite indexes are only used when the leftmost column(s) of the index appear in the `WHERE` clause. An index on `(user_id, created_at, status)` cannot accelerate a query with only `WHERE status = ?`.

---

## Verification

```bash
# Run EXPLAIN QUERY PLAN on the main query
wrangler d1 execute DB --remote --command \
  "EXPLAIN QUERY PLAN SELECT id, title FROM items WHERE user_id='u1' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 20;"

# List all indexes
wrangler d1 execute DB --remote --command \
  "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='items';"

# Analyze table to populate sqlite_stat1
wrangler d1 execute DB --remote --command "ANALYZE items;"
wrangler d1 execute DB --remote --command "SELECT * FROM sqlite_stat1 WHERE tbl='items';"
```

---

## Related

- `d1-row-level-security-workers.md`
- `d1-schema-migration-wrangler-workflow.md`
- `d1-full-text-search-fts5-workers.md`

---

## Sources

- SQLite Query Planner documentation — https://www.sqlite.org/queryplanner.html
- SQLite Partial Indexes — https://www.sqlite.org/partialindex.html
- SQLite Generated Columns — https://www.sqlite.org/gencol.html
- Cloudflare D1 query API — https://developers.cloudflare.com/d1/worker-api/
