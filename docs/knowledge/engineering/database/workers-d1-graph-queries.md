# Graph-Style Queries in D1 with Recursive CTEs

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have hierarchical data — an org chart, a comment thread, a category tree, a bill-of-materials — stored as an adjacency list in D1. A naive recursive TypeScript loop to fetch descendants makes N database round-trips. You need a single SQL query that traverses the tree to arbitrary depth, with cycle protection, depth limits, and path tracking.

---

## Context

SQLite (and D1) supports recursive CTEs via `WITH RECURSIVE`. A recursive CTE has two parts:
1. **Anchor** — the starting set (e.g., the root node).
2. **Recursive member** — joins the CTE to the base table to walk one level deeper.

SQLite's recursive CTEs handle breadth-first traversal by default. Depth-first requires ordering tricks. Cycle detection requires carrying a visited-key string through the recursion.

For very deep trees (hundreds of levels), the nested set model is faster for reads but expensive to write. For trees with frequent writes and moderate depth (< 50 levels), the adjacency list + recursive CTE approach is the right default.

---

## Solution

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
}

export interface OrgNode {
  id: string;
  parent_id: string | null;
  name: string;
  role: string;
}

export interface TreeNode extends OrgNode {
  depth: number;
  path: string;    // e.g. "root/engineering/backend"
  children?: TreeNode[];
}

// src/org-tree.ts
export class OrgTreeRepository {
  constructor(private db: D1Database) {}

  /**
   * Fetch the full subtree rooted at `rootId` using a recursive CTE.
   * Returns rows in breadth-first order with depth and materialized path.
   *
   * Depth is capped at `maxDepth` to prevent runaway queries.
   * Cycle detection: `path` column is checked for the current id before recursing.
   */
  async getSubtree(
    rootId: string,
    maxDepth = 10
  ): Promise<TreeNode[]> {
    const result = await this.db
      .prepare(
        `WITH RECURSIVE subtree(id, parent_id, name, role, depth, path, visited) AS (
           -- Anchor: the root node
           SELECT
             n.id,
             n.parent_id,
             n.name,
             n.role,
             0 AS depth,
             n.name AS path,
             ',' || n.id || ',' AS visited
           FROM org_nodes n
           WHERE n.id = ?

           UNION ALL

           -- Recursive member: one level deeper
           SELECT
             n.id,
             n.parent_id,
             n.name,
             n.role,
             s.depth + 1,
             s.path || '/' || n.name,
             s.visited || n.id || ','
           FROM org_nodes n
           JOIN subtree s ON n.parent_id = s.id
           WHERE s.depth < ?                       -- depth limit
             AND s.visited NOT LIKE '%,' || n.id || ',%'  -- cycle guard
         )
         SELECT id, parent_id, name, role, depth, path
         FROM subtree
         ORDER BY depth ASC, name ASC`
      )
      .bind(rootId, maxDepth)
      .all<TreeNode>();

    return result.results;
  }

  /**
   * Fetch ancestors of a node up to the root (upward traversal).
   * Useful for breadcrumb rendering.
   */
  async getAncestors(nodeId: string): Promise<TreeNode[]> {
    const result = await this.db
      .prepare(
        `WITH RECURSIVE ancestors(id, parent_id, name, role, depth, path) AS (
           SELECT n.id, n.parent_id, n.name, n.role, 0, n.name
           FROM org_nodes n
           WHERE n.id = ?

           UNION ALL

           SELECT n.id, n.parent_id, n.name, n.role, a.depth + 1, n.name || '/' || a.path
           FROM org_nodes n
           JOIN ancestors a ON n.id = a.parent_id
           WHERE a.depth < 50
         )
         SELECT id, parent_id, name, role, depth, path
         FROM ancestors
         ORDER BY depth DESC`  -- root first
      )
      .bind(nodeId)
      .all<TreeNode>();

    return result.results;
  }

  /**
   * Fetch a comment thread with nested replies (depth-first, flattened).
   * Orders by path so children appear right after their parent.
   */
  async getCommentThread(rootCommentId: string): Promise<TreeNode[]> {
    const result = await this.db
      .prepare(
        `WITH RECURSIVE thread(id, parent_id, name, role, depth, sort_path) AS (
           SELECT c.id, c.parent_id, c.body, c.author, 0,
                  printf('%010d', c.created_order) AS sort_path
           FROM comments c
           WHERE c.id = ?

           UNION ALL

           SELECT c.id, c.parent_id, c.body, c.author, t.depth + 1,
                  t.sort_path || '/' || printf('%010d', c.created_order)
           FROM comments c
           JOIN thread t ON c.parent_id = t.id
           WHERE t.depth < 20
         )
         SELECT id, parent_id, name AS body, role AS author, depth, sort_path AS path
         FROM thread
         ORDER BY sort_path ASC`
      )
      .bind(rootCommentId)
      .all<TreeNode>();

    return result.results;
  }

  /**
   * Convert flat rows into a nested tree structure.
   * Input must be sorted breadth-first (depth ASC) — as returned by getSubtree.
   */
  buildTree(rows: TreeNode[]): TreeNode | null {
    if (rows.length === 0) return null;

    const map = new Map<string, TreeNode>();
    for (const row of rows) {
      map.set(row.id, { ...row, children: [] });
    }

    let root: TreeNode | null = null;
    for (const row of rows) {
      const node = map.get(row.id)!;
      if (!row.parent_id || !map.has(row.parent_id)) {
        root = node;
      } else {
        map.get(row.parent_id)!.children!.push(node);
      }
    }
    return root;
  }

  /**
   * Count descendants without fetching them — fast aggregate via CTE.
   */
  async countDescendants(rootId: string): Promise<number> {
    const result = await this.db
      .prepare(
        `WITH RECURSIVE sub(id) AS (
           SELECT id FROM org_nodes WHERE id = ?
           UNION ALL
           SELECT n.id FROM org_nodes n JOIN sub s ON n.parent_id = s.id
         )
         SELECT COUNT(*) - 1 AS count FROM sub`  -- subtract root itself
      )
      .bind(rootId)
      .first<{ count: number }>();
    return result?.count ?? 0;
  }

  /**
   * Move a subtree to a new parent — checks for cycles before updating.
   */
  async moveSubtree(nodeId: string, newParentId: string): Promise<void> {
    // Prevent moving a node under one of its own descendants.
    const descendants = await this.getSubtree(nodeId, 100);
    const descendantIds = new Set(descendants.map(d => d.id));
    if (descendantIds.has(newParentId)) {
      throw new Error(`Cannot move node ${nodeId} under its own descendant ${newParentId}`);
    }

    await this.db
      .prepare('UPDATE org_nodes SET parent_id = ? WHERE id = ?')
      .bind(newParentId, nodeId)
      .run();
  }
}

// src/worker.ts
import { OrgTreeRepository } from './org-tree';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const repo = new OrgTreeRepository(env.DB);

    const subtreeMatch = url.pathname.match(/^\/org\/([\w-]+)\/subtree$/);
    if (subtreeMatch && request.method === 'GET') {
      const maxDepth = parseInt(url.searchParams.get('depth') ?? '10', 10);
      const rows = await repo.getSubtree(subtreeMatch[1], Math.min(maxDepth, 20));
      const tree = repo.buildTree(rows);
      return Response.json(tree);
    }

    const ancestorsMatch = url.pathname.match(/^\/org\/([\w-]+)\/ancestors$/);
    if (ancestorsMatch && request.method === 'GET') {
      const rows = await repo.getAncestors(ancestorsMatch[1]);
      return Response.json(rows);
    }

    const countMatch = url.pathname.match(/^\/org\/([\w-]+)\/count$/);
    if (countMatch && request.method === 'GET') {
      const count = await repo.countDescendants(countMatch[1]);
      return Response.json({ count });
    }

    return new Response('Not Found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

**Schema:**
```sql
CREATE TABLE org_nodes (
  id        TEXT PRIMARY KEY,
  parent_id TEXT REFERENCES org_nodes(id) ON DELETE CASCADE,
  name      TEXT NOT NULL,
  role      TEXT NOT NULL DEFAULT ''
);

-- Index for "get children of parent" joins in the recursive member.
CREATE INDEX idx_org_nodes_parent ON org_nodes (parent_id);

CREATE TABLE comments (
  id            TEXT PRIMARY KEY,
  parent_id     TEXT REFERENCES comments(id) ON DELETE CASCADE,
  body          TEXT NOT NULL,
  author        TEXT NOT NULL,
  created_order INTEGER NOT NULL  -- monotonic integer, not timestamp, for deterministic sort
);

CREATE INDEX idx_comments_parent ON comments (parent_id);
```

**Recursive CTE anatomy:**
- `UNION ALL` (not `UNION`) is required — `UNION` deduplicates, which breaks cycle detection via the `visited` string.
- The `visited NOT LIKE '%,id,%'` guard prevents infinite loops on graphs with back-edges. The `,` delimiters prevent substring false-positives (`id=1` matching `id=10`).
- SQLite processes the recursive member iteratively — it does not stack-overflow for deep trees, but it does serialize, so very wide trees (millions of children per level) are slow.

**Depth-first ordering trick:** Use `sort_path` (a zero-padded string built by concatenation) to sort nodes in depth-first pre-order. The concatenated path string grows with depth, so lexicographic sort on `sort_path` produces the correct depth-first sequence.

**Nested set model comparison:**

| | Adjacency list + recursive CTE | Nested set model |
|---|---|---|
| Read subtree | O(n) CTE traversal | O(1) range query |
| Insert node | O(1) | O(n) re-numbering |
| Move subtree | O(depth) cycle check | O(n) re-numbering |
| Depth limit | Simple WHERE clause | Requires counting ancestors |
| Best for | Write-heavy trees | Read-heavy, rarely restructured |

---

## Anti-patterns

```typescript
// BAD: recursive TypeScript function making N database round-trips
async function fetchChildren(id: string): Promise<OrgNode[]> {
  const children = await db.prepare('SELECT * FROM org_nodes WHERE parent_id = ?').bind(id).all();
  const nested = await Promise.all(
    children.results.map(child => fetchChildren(child.id)) // N + N^2 + ... queries
  );
  return children.results;
}

// BAD: missing depth limit in recursive CTE — a cycle causes infinite loop
// 'WITH RECURSIVE sub AS (... UNION ALL SELECT ... FROM sub JOIN ...)'  -- no WHERE depth < N
// SQLite will run until it exhausts memory.

// BAD: UNION instead of UNION ALL in recursive CTE
// UNION deduplicates by value, not by graph structure, and breaks cycle detection.
```

---

## Gotchas

- **SQLite recursion limit:** SQLite caps recursive CTE iterations at `SQLITE_MAX_PAGE_COUNT * page_size` by default, but Cloudflare D1 may impose a lower limit. Always cap depth explicitly with `WHERE depth < N`.
- **`visited NOT LIKE` is O(depth) string scan per row.** For trees you control with no back-edges (strict trees), omit the cycle guard for performance. For general graphs (e.g., tag graphs, social follows), keep it.
- **`ON DELETE CASCADE` in SQLite requires `PRAGMA foreign_keys = ON`.** D1 enables foreign keys by default, but verify with `PRAGMA foreign_keys;` returning `1` before relying on cascade deletes.
- **`printf('%010d', created_order)`** pads to 10 digits ensuring lexicographic sort matches numeric sort up to 9 999 999 999 — adjust padding if your `created_order` exceeds this range.
- **`buildTree` assumes a single connected component.** If `getSubtree` returns multiple roots (a bug), the function returns only one. Add a guard: `if (rows.filter(r => !r.parent_id).length > 1) throw new Error('Multiple roots')`.

---

## Verification

```typescript
// test/graph.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { OrgTreeRepository } from '../src/org-tree';

describe('Recursive CTE graph queries', () => {
  let repo: OrgTreeRepository;

  beforeEach(async () => {
    const db = getMiniflareD1('DB');
    await db.exec(SCHEMA_SQL);
    // Seed: ceo -> [cto, cfo] -> cto -> [eng1, eng2]
    await db.exec(`
      INSERT INTO org_nodes VALUES ('ceo',  NULL,   'CEO',  'exec');
      INSERT INTO org_nodes VALUES ('cto',  'ceo',  'CTO',  'exec');
      INSERT INTO org_nodes VALUES ('cfo',  'ceo',  'CFO',  'exec');
      INSERT INTO org_nodes VALUES ('eng1', 'cto',  'Eng1', 'ic');
      INSERT INTO org_nodes VALUES ('eng2', 'cto',  'Eng2', 'ic');
    `);
    repo = new OrgTreeRepository(db);
  });

  it('getSubtree returns all descendants', async () => {
    const rows = await repo.getSubtree('ceo');
    expect(rows).toHaveLength(5);
  });

  it('getSubtree respects depth limit', async () => {
    const rows = await repo.getSubtree('ceo', 1);
    const ids = rows.map(r => r.id);
    expect(ids).toContain('ceo');
    expect(ids).toContain('cto');
    expect(ids).not.toContain('eng1'); // depth 2, excluded
  });

  it('getAncestors returns path to root', async () => {
    const rows = await repo.getAncestors('eng1');
    expect(rows.map(r => r.id)).toEqual(['ceo', 'cto', 'eng1']);
  });

  it('countDescendants excludes the root itself', async () => {
    const count = await repo.countDescendants('cto');
    expect(count).toBe(2); // eng1, eng2
  });

  it('moveSubtree prevents moving under own descendant', async () => {
    await expect(repo.moveSubtree('cto', 'eng1')).rejects.toThrow();
  });
});
```

---

## Related

- `workers-d1-schema-versioning.md` — migrations for adding `parent_id` columns to existing tables
- `workers-d1-soft-delete-pattern.md` — soft-deleting tree nodes while preserving subtree structure
- `workers-d1-pagination-cursor.md` — paginating large flat result sets from CTE queries

---

## Sources

- SQLite recursive CTEs: https://www.sqlite.org/lang_with.html
- "Trees in SQL" — Joe Celko: https://www.ibase.ru/files/articles/programming/dbmstrees/sqltrees.html
- Nested sets vs adjacency list: https://mikehillyer.com/articles/managing-hierarchical-data-in-mysql/
