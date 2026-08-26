# D1 Partial Indexes with WHERE Clause in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your D1 table has millions of rows but most queries filter on a small subset — for example, only `active` users or only `pending` orders. Full indexes on those columns waste space indexing rows you never query. Partial indexes let you index only the rows that match a fixed predicate, making the index smaller and lookups faster.

## Context

D1 runs on SQLite under the hood, and SQLite has supported partial indexes (indexes with a `WHERE` clause) since version 3.8.9. A partial index stores index entries only for rows where the `WHERE` predicate is true. This reduces the index B-tree size proportionally to how selective the predicate is. Workers that query a filtered subset of a large table benefit the most: the query planner will choose the partial index when the query's `WHERE` clause implies the index predicate, cutting both I/O and CPU time inside the D1 edge instance.

## Schema and Index Creation

```sql
-- Base table
CREATE TABLE IF NOT EXISTS users (
  id        TEXT PRIMARY KEY,
  email     TEXT NOT NULL,
  status    TEXT NOT NULL DEFAULT 'pending', -- 'active' | 'pending' | 'banned'
  plan      TEXT NOT NULL DEFAULT 'free',
  created_at INTEGER NOT NULL
);

-- Full index (indexes ALL rows — avoid on large tables with low-cardinality status)
-- CREATE INDEX idx_users_email ON users(email);

-- Partial index: only active users
-- If 10 % of rows are active, this index is 10x smaller
CREATE INDEX IF NOT EXISTS idx_active_users_email
  ON users(email)
  WHERE status = 'active';

-- Partial index: pending orders created in the last 30 days
CREATE TABLE IF NOT EXISTS orders (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'pending',
  total_cents INTEGER NOT NULL,
  created_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pending_orders_user
  ON orders(user_id, created_at DESC)
  WHERE status = 'pending';
```

## Workers Query Patterns That Benefit

```typescript
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // This query matches the partial index predicate exactly.
    // SQLite planner will use idx_active_users_email.
    if (url.pathname === '/users/lookup') {
      const email = url.searchParams.get('email') ?? '';
      const result = await env.DB.prepare(
        `SELECT id, email, plan
         FROM users
         WHERE status = 'active'
           AND email = ?`
      )
        .bind(email)
        .first<{ id: string; email: string; plan: string }>();

      if (!result) return new Response('Not found', { status: 404 });
      return Response.json(result);
    }

    // Pending orders for a user — uses idx_pending_orders_user
    if (url.pathname === '/orders/pending') {
      const userId = url.searchParams.get('user_id') ?? '';
      const { results } = await env.DB.prepare(
        `SELECT id, total_cents, created_at
         FROM orders
         WHERE status = 'pending'
           AND user_id = ?
         ORDER BY created_at DESC
         LIMIT 50`
      )
        .bind(userId)
        .all();

      return Response.json(results);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Verifying the Partial Index Is Used

```sql
-- Run via D1 console or wrangler d1 execute
EXPLAIN QUERY PLAN
  SELECT id, email, plan
  FROM users
  WHERE status = 'active'
    AND email = 'alice@example.com';

-- Expected output (look for the index name):
-- SEARCH users USING INDEX idx_active_users_email (email=?)

-- If you see SCAN users, the planner skipped the index.
-- Check that your query WHERE clause implies the index predicate.
```

## Limitations

- **OR conditions** — A query like `WHERE status = 'active' OR status = 'pending'` cannot use a partial index defined on `status = 'active'` alone. Create a separate index or use a full index.
- **Predicate mismatch** — `WHERE status != 'banned'` does NOT imply `WHERE status = 'active'`, so the partial index will not be used even if the result sets overlap.
- **Dynamic predicates** — The index `WHERE` clause must be a constant expression. You cannot use bound parameters in the index definition itself.
- **`NOT NULL` partial indexes** — `WHERE col IS NOT NULL` is a valid and very useful partial index pattern for sparse nullable columns.
- **D1 replication lag** — Partial indexes are created synchronously on the primary but may take a moment to propagate to read replicas. Run read-heavy queries against the primary immediately after DDL changes during migrations.

## Anti-patterns

- **Partial index with low selectivity** — `WHERE status != 'deleted'` on a table where 99 % of rows are not deleted creates a nearly full index; a regular index is simpler.
- **Querying without the predicate** — `SELECT * FROM users WHERE email = ?` (no `status` filter) will not use `idx_active_users_email`; you get a full scan instead.
- **Forgetting to recreate after `DROP TABLE`** — Partial indexes are dropped with the table; your migration must re-create them.

## Gotchas

- SQLite's query planner uses partial indexes only when it can prove the query's `WHERE` clause is at least as restrictive as the index predicate.
- `EXPLAIN QUERY PLAN` output in D1 console omits the literal SQL; use `wrangler d1 execute <DB> --command "EXPLAIN QUERY PLAN ..."` for full output.
- Partial indexes do not appear in `PRAGMA index_list(table)` output differently from full indexes; check `PRAGMA index_info` and `sqlite_master` for the `WHERE` clause.
- Cloudflare D1 enforces a per-database index count limit; use partial indexes to stay within it on tables with many filter patterns.

## Verification

```bash
# Create the schema and inspect the index
wrangler d1 execute example project-db --file=migrations/001_partial_indexes.sql

# Verify the index exists with its WHERE clause
wrangler d1 execute example project-db \
  --command "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='users';"

# Run EXPLAIN QUERY PLAN to confirm index usage
wrangler d1 execute example project-db \
  --command "EXPLAIN QUERY PLAN SELECT id FROM users WHERE status='active' AND email='test@example.com';"
```

## Related

- `d1-online-schema-change-zero-downtime-workers.md`
- `d1-generated-columns-computed-fields-workers.md`
- `d1-row-versioning-optimistic-locking-workers.md`

## Sources

- SQLite Partial Indexes — https://www.sqlite.org/partialindex.html
- Cloudflare D1 Documentation — https://developers.cloudflare.com/d1/
- SQLite EXPLAIN QUERY PLAN — https://www.sqlite.org/eqp.html
