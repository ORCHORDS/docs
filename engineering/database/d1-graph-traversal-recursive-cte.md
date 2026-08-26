# D1 Graph Traversal with Recursive CTEs

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You store a parent–child hierarchy or a directed graph in D1 — folder trees, org charts,
permission hierarchies, dependency graphs — and need to walk the entire reachable subgraph
from a root node without N+1 Worker round-trips. You want a single SQL query that returns
all descendants (or ancestors) to an arbitrary depth.

## Context

D1 runs SQLite 3.39+, which fully supports `WITH RECURSIVE` common table expressions (CTEs).
Recursive CTEs let you traverse adjacency-list tables in pure SQL, eliminating the application
loop that would otherwise require one D1 round-trip per level. SQLite's recursive CTE engine
uses a queue internally, so cycles in the graph must be guarded at the application layer or via
a visited-set check in the CTE `WHERE` clause. D1's per-query row limit is 1 000 by default for
`.first()` / `.all()` — use `.raw()` for large traversals.

---

## Schema Design

```sql
-- Adjacency list: supports multi-parent graphs (not just trees)
CREATE TABLE nodes (
  id          TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  node_type   TEXT NOT NULL DEFAULT 'default',
  metadata    TEXT,            -- JSON
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE edges (
  from_id     TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  to_id       TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  edge_type   TEXT NOT NULL DEFAULT 'child',
  weight      REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (from_id, to_id, edge_type)
);

-- Critical: index both directions for BFS in either direction
CREATE INDEX idx_edges_from ON edges(from_id, edge_type);
CREATE INDEX idx_edges_to   ON edges(to_id,   edge_type);
```

---

## Descendant Traversal (Top-Down BFS)

```sql
-- All nodes reachable from :rootId, with depth and path tracking
WITH RECURSIVE descendants(id, depth, path) AS (
  -- Anchor: the root itself
  SELECT id, 0, id
  FROM   nodes
  WHERE  id = :rootId

  UNION ALL

  -- Recursive: follow edges one level deeper
  SELECT e.to_id, d.depth + 1, d.path || '/' || e.to_id
  FROM   descendants d
  JOIN   edges e ON e.from_id = d.id AND e.edge_type = 'child'
  -- Cycle guard: stop if we have already visited this node in this path
  WHERE  instr(d.path, e.to_id) = 0
    AND  d.depth < 20            -- hard depth cap
)
SELECT n.id, n.label, n.node_type, d.depth, d.path
FROM   descendants d
JOIN   nodes n ON n.id = d.id
ORDER  BY d.depth, n.label;
```

---

## Ancestor Traversal (Bottom-Up BFS)

```typescript
// src/graph/ancestors.ts
import { D1Database } from '@cloudflare/workers-types';

export interface GraphNode {
  id: string;
  label: string;
  node_type: string;
  depth: number;
  path: string;
}

export async function getAncestors(
  db: D1Database,
  nodeId: string,
  edgeType = 'child',
  maxDepth = 20,
): Promise<GraphNode[]> {
  const result = await db
    .prepare(
      `WITH RECURSIVE ancestors(id, depth, path) AS (
         SELECT id, 0, id FROM nodes WHERE id = ?1
         UNION ALL
         SELECT e.from_id, a.depth + 1, e.from_id || '/' || a.path
         FROM   ancestors a
         JOIN   edges e ON e.to_id = a.id AND e.edge_type = ?2
         WHERE  instr(a.path, e.from_id) = 0
           AND  a.depth < ?3
       )
       SELECT n.id, n.label, n.node_type, a.depth, a.path
       FROM   ancestors a
       JOIN   nodes n ON n.id = a.id
       WHERE  a.id != ?1
       ORDER  BY a.depth, n.label`,
    )
    .bind(nodeId, edgeType, maxDepth)
    .all<GraphNode>();

  return result.results;
}
```

---

## Shortest Path Between Two Nodes

```typescript
// src/graph/shortest-path.ts
import { D1Database } from '@cloudflare/workers-types';

export async function shortestPath(
  db: D1Database,
  fromId: string,
  toId: string,
  maxDepth = 15,
): Promise<string[] | null> {
  // BFS via recursive CTE; returns the first path found (shortest by hop count)
  const row = await db
    .prepare(
      `WITH RECURSIVE bfs(current_id, path, depth) AS (
         SELECT id, id, 0 FROM nodes WHERE id = ?1
         UNION ALL
         SELECT e.to_id,
                bfs.path || ',' || e.to_id,
                bfs.depth + 1
         FROM   bfs
         JOIN   edges e ON e.from_id = bfs.current_id
         WHERE  instr(bfs.path, e.to_id) = 0
           AND  bfs.depth < ?3
       )
       SELECT path FROM bfs
       WHERE  current_id = ?2
       ORDER  BY depth
       LIMIT  1`,
    )
    .bind(fromId, toId, maxDepth)
    .first<{ path: string }>();

  return row ? row.path.split(',') : null;
}
```

---

## Worker Handler: Subgraph Endpoint

```typescript
// src/workers/graph-worker.ts
import { D1Database } from '@cloudflare/workers-types';
import { getAncestors } from '../graph/ancestors';

interface Env { DB: D1Database }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const nodeId = url.searchParams.get('id');
    const direction = url.searchParams.get('dir') ?? 'descendants';

    if (!nodeId) return new Response('Missing id', { status: 400 });

    if (direction === 'ancestors') {
      const nodes = await getAncestors(env.DB, nodeId);
      return Response.json({ nodeId, direction, nodes });
    }

    // Descendants via direct D1 prepare
    const result = await env.DB.prepare(
      `WITH RECURSIVE desc(id, depth, path) AS (
         SELECT id, 0, id FROM nodes WHERE id = ?1
         UNION ALL
         SELECT e.to_id, d.depth + 1, d.path || '/' || e.to_id
         FROM   desc d
         JOIN   edges e ON e.from_id = d.id AND e.edge_type = 'child'
         WHERE  instr(d.path, e.to_id) = 0 AND d.depth < 20
       )
       SELECT n.id, n.label, n.node_type, d.depth
       FROM   desc d JOIN nodes n ON n.id = d.id
       ORDER  BY d.depth, n.label`,
    )
      .bind(nodeId)
      .all();

    return Response.json({ nodeId, direction, nodes: result.results });
  },
};
```

---

## Anti-patterns

- **No cycle guard in recursive CTE**: Without `WHERE instr(path, e.to_id) = 0`, a cyclic
  graph loops until SQLite hits its recursion limit and raises `SQLITE_ERROR`. Always include
  a path-visited check or a hard depth cap.
- **Fetching the full graph client-side and traversing in JS**: Multiple round-trips per level
  multiply D1 HTTP latency. One recursive CTE = one round-trip.
- **Using a closure/materialized path table without keeping it in sync**: Pre-computed closure
  tables go stale on graph mutations. Use recursive CTEs for dynamic traversal or maintain the
  closure table via triggers.
- **Path string concatenation with large IDs at deep depths**: If IDs are UUIDs (36 chars) and
  depth is 20, the path string reaches ~740 characters per row. Use short surrogate integer IDs
  or a separate visited-set table for very deep graphs.

## Gotchas

- SQLite's `WITH RECURSIVE` uses a FIFO queue (BFS order), not DFS. The first path found in
  BFS is the shortest hop-count path, but not necessarily the minimum-weight path.
- `instr(path, id)` checks substring containment, which produces false positives if one node ID
  is a prefix of another (e.g., `"a"` matches inside `"ab"`). Use a delimiter:
  `instr(',' || path || ',', ',' || e.to_id || ',') = 0`.
- D1's HTTP API does not stream rows. Very wide graphs (10 000+ nodes) should paginate by
  depth level or use D1's `.raw()` method to reduce per-row overhead.
- Recursive CTEs count against D1's statement complexity limits. Queries that exceed SQLite's
  internal `SQLITE_MAX_EXPR_DEPTH` (default 1000) may fail; this is rarely hit in graph
  traversal but possible with compound nested CTEs.

## Verification

```sql
-- Confirm edge index is used in the recursive step (look for 'SEARCH edges USING INDEX')
EXPLAIN QUERY PLAN
WITH RECURSIVE desc(id, depth) AS (
  SELECT id, 0 FROM nodes WHERE id = 'root-1'
  UNION ALL
  SELECT e.to_id, d.depth + 1
  FROM desc d JOIN edges e ON e.from_id = d.id
  WHERE d.depth < 5
)
SELECT id, depth FROM desc;

-- Count distinct reachable nodes from a given root
WITH RECURSIVE desc(id, depth) AS (
  SELECT id, 0 FROM nodes WHERE id = 'root-1'
  UNION ALL
  SELECT e.to_id, d.depth + 1 FROM desc d
  JOIN edges e ON e.from_id = d.id WHERE d.depth < 20
)
SELECT COUNT(DISTINCT id) AS reachable FROM desc;
```

## Related

- `sqlite-recursive-cte-graph-queries.md` — generic SQLite recursive CTE patterns
- `d1-json-column-patterns.md` — storing node metadata as JSON
- `d1-foreign-keys-referential-integrity.md` — cascade deletes on edge removal
- `hierarchical-data-ltree.md` — Postgres ltree alternative for comparison
- `cte-common-table-expressions.md` — non-recursive CTE fundamentals

## Sources

- SQLite WITH RECURSIVE: https://www.sqlite.org/lang_with.html
- Cloudflare D1 Query API: https://developers.cloudflare.com/d1/worker-api/d1-database/
- SQLite BFS graph traversal: https://www.sqlite.org/lang_with.html#recursive_query_examples
