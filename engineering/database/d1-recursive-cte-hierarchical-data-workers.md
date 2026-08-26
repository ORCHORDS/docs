# D1 Recursive CTE Hierarchical Data in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

An anonymous social platform (example project / example.com) needs to render nested comment threads,
category trees, or organizational follower graphs stored in Cloudflare D1. Fetching parent-child
relationships one level at a time produces N+1 query patterns and degrades edge performance.
Recursive CTEs let a single SQL statement walk an entire tree depth.

## Context

Cloudflare D1 is built on SQLite, which has supported `WITH RECURSIVE` since version 3.8.3.
Workers execute queries through D1's HTTP-based binding (`env.DB`) — each `prepare().bind().all()`
call is an atomic SQL round-trip. Recursive CTEs avoid multiple round-trips by collapsing tree
traversal into one SQL statement executed server-side in D1's SQLite engine.

## Adjacency List Schema

The simplest hierarchical model stores a `parent_id` self-reference. SQLite enforces the foreign
key only when `PRAGMA foreign_keys = ON` is set per connection; D1 enables it by default.

```sql
CREATE TABLE comments (
  id         INTEGER PRIMARY KEY,
  post_id    INTEGER NOT NULL,
  parent_id  INTEGER REFERENCES comments(id) ON DELETE CASCADE,
  author_id  INTEGER NOT NULL,
  body       TEXT    NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  depth      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_comments_post_parent ON comments(post_id, parent_id);
CREATE INDEX idx_comments_parent      ON comments(parent_id);
```

## Recursive CTE — Fetch Full Thread

The anchor member selects root comments (`parent_id IS NULL`) for a given post. The recursive
member joins each child row to the accumulated result set. `depth` is computed inline so the
application can indent replies without extra round-trips.

```sql
WITH RECURSIVE thread(
  id, parent_id, author_id, body, created_at, depth
) AS (
  -- anchor: root comments for the post
  SELECT id, parent_id, author_id, body, created_at, 0
  FROM   comments
  WHERE  post_id = ?1 AND parent_id IS NULL

  UNION ALL

  -- recursive: children of already-selected rows
  SELECT c.id, c.parent_id, c.author_id, c.body, c.created_at, t.depth + 1
  FROM   comments c
  JOIN   thread   t ON c.parent_id = t.id
  WHERE  c.post_id = ?1
)
SELECT * FROM thread
ORDER BY created_at;
```

In TypeScript inside a Worker:

```typescript
export interface Env {
  DB: D1Database;
}

interface CommentRow {
  id: number;
  parent_id: number | null;
  author_id: number;
  body: string;
  created_at: number;
  depth: number;
}

const THREAD_SQL = `
WITH RECURSIVE thread(id, parent_id, author_id, body, created_at, depth) AS (
  SELECT id, parent_id, author_id, body, created_at, 0
  FROM   comments
  WHERE  post_id = ?1 AND parent_id IS NULL
  UNION ALL
  SELECT c.id, c.parent_id, c.author_id, c.body, c.created_at, t.depth + 1
  FROM   comments c
  JOIN   thread   t ON c.parent_id = t.id
  WHERE  c.post_id = ?1
)
SELECT * FROM thread ORDER BY created_at
`;

export async function fetchThread(
  env: Env,
  postId: number
): Promise<CommentRow[]> {
  const { results } = await env.DB.prepare(THREAD_SQL)
    .bind(postId)
    .all<CommentRow>();
  return results;
}
```

## Optimization — Depth Cap and Early Exit

Unbounded recursion on a pathological data set can stall a D1 query. Cap depth with a `WHERE`
guard in the recursive member and use SQLite's built-in `RECURSIVE_LIMIT` pragma alternative:

```sql
WITH RECURSIVE thread(...) AS (
  -- anchor unchanged
  SELECT id, parent_id, author_id, body, created_at, 0
  FROM comments WHERE post_id = ?1 AND parent_id IS NULL
  UNION ALL
  SELECT c.id, c.parent_id, c.author_id, c.body, c.created_at, t.depth + 1
  FROM comments c
  JOIN thread t ON c.parent_id = t.id
  WHERE c.post_id = ?1
    AND t.depth < 10   -- hard cap at 10 levels
)
SELECT * FROM thread ORDER BY created_at;
```

Alternatively insert a `depth` column into the base table and index it; then the recursive
member can filter `c.depth <= 10` using the stored value without computing it at runtime.

## Materialized Path Alternative

When read performance is critical and writes are infrequent, store the full ancestry path as a
text column. This trades write complexity for O(1) subtree reads via a prefix scan.

```sql
ALTER TABLE comments ADD COLUMN path TEXT NOT NULL DEFAULT '';

-- On insert, build path from parent:
-- path = parent.path || '/' || new_id
-- Example rows: '/', '/1/', '/1/42/', '/1/42/99/'

CREATE INDEX idx_comments_path ON comments(path);

-- Fetch entire subtree:
SELECT * FROM comments
WHERE path LIKE ?1 || '%'
  AND post_id = ?2
ORDER BY path;
```

```typescript
async function fetchSubtree(env: Env, rootPath: string, postId: number) {
  return env.DB.prepare(
    `SELECT * FROM comments WHERE path LIKE ?1 AND post_id = ?2 ORDER BY path`
  )
    .bind(`${rootPath}%`, postId)
    .all<CommentRow>();
}
```

## Anti-patterns

- Fetching one level at a time in a loop — causes N+1 round-trips across the Cloudflare edge
- Omitting a depth cap on the recursive member — allows denial-of-service via deeply nested data
- Using `UNION` instead of `UNION ALL` inside a recursive CTE — `UNION` deduplicates rows and breaks the recursion termination semantics in SQLite
- Storing tree structure only in application state — makes server-side filtering impossible

## Gotchas

- SQLite's `WITH RECURSIVE` uses `UNION ALL` for recursion, not `UNION`; confusing them silently limits recursion to distinct rows
- D1 does not support `PRAGMA recursive_triggers`; avoid triggers that call themselves
- The `depth` expression must appear in the SELECT list of the anchor to be referenced in the recursive member
- Materialized path columns must be updated atomically when reparenting a node — use a transaction via `env.DB.batch()`

## Verification

```typescript
// Seed a three-level tree and assert shape
const seed = env.DB.batch([
  env.DB.prepare(`INSERT INTO comments(id,post_id,parent_id,author_id,body) VALUES(1,1,NULL,10,'root')`),
  env.DB.prepare(`INSERT INTO comments(id,post_id,parent_id,author_id,body) VALUES(2,1,1,11,'child')`),
  env.DB.prepare(`INSERT INTO comments(id,post_id,parent_id,author_id,body) VALUES(3,1,2,12,'grandchild')`),
]);
await seed;
const rows = await fetchThread(env, 1);
console.assert(rows.length === 3);
console.assert(rows[2].depth === 2);
```

## Related

- `/documentation/categories/database/d1-graph-traversal-recursive-cte.md`
- `/documentation/categories/database/sqlite-recursive-cte-graph-queries.md`
- `/documentation/categories/database/d1-pagination-cursor-keyset.md`
- `/documentation/categories/database/d1-foreign-keys-referential-integrity.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/lang_with.html
- https://developers.cloudflare.com/d1/build-with-d1/d1-client-api/
