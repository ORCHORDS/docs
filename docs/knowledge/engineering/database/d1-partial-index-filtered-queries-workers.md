# D1 Partial Index Filtered Queries in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

On example project / example.com, most queries filter on a small subset of rows — active posts,
unread notifications, pending moderation flags. Full-table indexes scan millions of historical
rows to find a few thousand relevant ones, wasting D1 query time and CPU budget. A partial
index (also called a filtered index in SQLite) indexes only the rows that match a `WHERE`
predicate, making these hot-path queries dramatically faster with a fraction of the index size.

## Context

Cloudflare D1 runs SQLite 3.x, which has supported partial indexes via `CREATE INDEX ... WHERE`
since SQLite 3.8.9. Workers access D1 through the `env.DB` binding; the SQLite query planner
uses partial indexes automatically when the query's `WHERE` clause subsumes the index predicate.
No application-level hint is needed — correct index design is sufficient.

## Partial Index Syntax and Planner Rules

SQLite uses a partial index only when the query's WHERE clause logically implies the index
predicate. For example, an index `WHERE deleted_at IS NULL` is used only when the query also
filters `WHERE deleted_at IS NULL`. If the query omits that filter the planner falls back to
a full-table scan or a different index.

```sql
-- Active posts only (deleted_at IS NULL covers ~95% of queries)
CREATE INDEX idx_posts_active_created
  ON posts(created_at DESC)
  WHERE deleted_at IS NULL;

-- Unread notifications (status = 'unread' is ~2% of the notifications table)
CREATE INDEX idx_notif_unread_user
  ON notifications(user_id, created_at DESC)
  WHERE status = 'unread';

-- Pending moderation flags
CREATE INDEX idx_flags_pending_type
  ON moderation_flags(content_type, content_id)
  WHERE resolved_at IS NULL;
```

## Implementation — Workers TypeScript

```typescript
export interface Env {
  DB: D1Database;
}

// This query uses idx_posts_active_created because WHERE deleted_at IS NULL
// is present and matches the index predicate exactly.
export async function getActivePosts(
  env: Env,
  limit = 20,
  beforeCreatedAt?: number
): Promise<D1Result<Record<string, unknown>>> {
  const cursor = beforeCreatedAt ?? Math.floor(Date.now() / 1000) + 1;
  return env.DB.prepare(`
    SELECT id, author_id, title, created_at
    FROM   posts
    WHERE  deleted_at IS NULL
      AND  created_at < ?1
    ORDER  BY created_at DESC
    LIMIT  ?2
  `)
    .bind(cursor, limit)
    .all();
}

// This query uses idx_notif_unread_user — status filter + user_id filter
export async function getUnreadNotifications(
  env: Env,
  userId: number
): Promise<D1Result<Record<string, unknown>>> {
  return env.DB.prepare(`
    SELECT id, type, payload, created_at
    FROM   notifications
    WHERE  status   = 'unread'
      AND  user_id  = ?1
    ORDER  BY created_at DESC
    LIMIT  50
  `)
    .bind(userId)
    .all();
}
```

## Optimization — Composite Partial Indexes

Combine partial filtering with composite columns so the index covers the entire query without
a table lookup (a covering partial index). Include all SELECT'd columns in the index definition
using additional columns in the index key or as `INCLUDE`-style trailing columns (SQLite does not
support the `INCLUDE` keyword; list them in the key instead, accepting a slightly larger index).

```sql
-- Covering partial index: planner can satisfy the query from the index alone
CREATE INDEX idx_posts_active_feed
  ON posts(author_id, created_at DESC, id, title)
  WHERE deleted_at IS NULL;
```

Verify coverage with `EXPLAIN QUERY PLAN`:

```sql
EXPLAIN QUERY PLAN
  SELECT id, author_id, title, created_at
  FROM   posts
  WHERE  deleted_at IS NULL
    AND  author_id  = 42
  ORDER  BY created_at DESC
  LIMIT  20;
-- Expected output: SEARCH posts USING INDEX idx_posts_active_feed (author_id=?)
```

In Workers, run EXPLAIN QUERY PLAN programmatically during development:

```typescript
async function explainQuery(env: Env, sql: string, ...bindings: unknown[]) {
  const { results } = await env.DB.prepare(`EXPLAIN QUERY PLAN ${sql}`)
    .bind(...bindings)
    .all<{ detail: string }>();
  console.log(results.map((r) => r.detail).join('\n'));
}
```

## Multi-Status Partial Indexes

When a column has only a few valid states and queries always target one state, create one
partial index per high-value state rather than a single full index on the column.

```sql
-- Two partial indexes instead of one full index on (status)
CREATE INDEX idx_jobs_queued   ON jobs(created_at) WHERE status = 'queued';
CREATE INDEX idx_jobs_running  ON jobs(started_at) WHERE status = 'running';

-- A query on status = 'completed' does NOT use either partial index;
-- it falls back to a full scan, which is acceptable if completed rows
-- are rarely queried or are archived to R2.
```

## Anti-patterns

- Creating a partial index whose predicate doesn't match any real query — the index is never used and wastes write overhead
- Using a partial index predicate that references a column updated frequently (e.g., `last_seen_at`) — every update rebuilds the index entry
- Expecting SQLite to use a partial index when the query's WHERE clause is a superset rather than a subset of the predicate — the planner requires the query to imply the predicate, not the reverse
- Dropping a partial index and replacing it with a full index "to be safe" — full indexes are larger and slower on the hot path

## Gotchas

- SQLite treats `WHERE deleted_at IS NULL` and `WHERE deleted_at ISNULL` as equivalent predicates; both phrases activate the same partial index
- Partial index predicates cannot reference subqueries, aggregate functions, or window functions
- Adding a column to the predicate that contains `NULL` requires careful `IS NULL` vs `= NULL` handling — `= NULL` never matches in SQLite
- D1 does not expose `ANALYZE`-gathered statistics; use `EXPLAIN QUERY PLAN` output and wall-clock timing in Wrangler tail logs to confirm index usage

## Verification

```sql
-- After creating the index, confirm it's used:
EXPLAIN QUERY PLAN
  SELECT id FROM notifications
  WHERE status = 'unread' AND user_id = 1;
-- Must mention idx_notif_unread_user, not a full scan.

-- Confirm index size vs full index:
SELECT name, tbl_name
FROM sqlite_master
WHERE type = 'index';
```

```typescript
// Smoke test: insert 1 000 read + 10 unread, assert query returns 10
const stmts = Array.from({ length: 1000 }, (_, i) =>
  env.DB.prepare(
    `INSERT INTO notifications(user_id,status,type,payload,created_at)
     VALUES(1,'read','like','{}',?1)`
  ).bind(i)
);
stmts.push(
  ...Array.from({ length: 10 }, (_, i) =>
    env.DB.prepare(
      `INSERT INTO notifications(user_id,status,type,payload,created_at)
       VALUES(1,'unread','mention','{}',?1)`
    ).bind(1000 + i)
  )
);
await env.DB.batch(stmts);
const { results } = await getUnreadNotifications(env, 1);
console.assert(results.length === 10, 'Expected 10 unread notifications');
```

## Related

- `/documentation/docs/policies/database/d1-json-columns-partial-indexes.md`
- `/documentation/docs/policies/database/partial-indexes.md`
- `/documentation/docs/policies/database/d1-covering-index-composite-key-workers.md`
- `/documentation/docs/policies/database/d1-analyze-query-planner-workers.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/partialindex.html
- https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/
- https://www.sqlite.org/lang_explain.html
