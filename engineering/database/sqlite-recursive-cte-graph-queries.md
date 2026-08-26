# Graph Queries in SQLite and D1 Using Recursive CTEs

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your application needs to traverse tree or graph structures stored in a relational
table: product category hierarchies, org charts, file-system folder trees, comment
threads, task dependency graphs, access-permission inheritance chains. You want to
avoid multiple round-trips to the database or loading entire trees into application
memory.

SQLite (and therefore D1) supports recursive common table expressions (CTEs) since
version 3.8.3. They handle the vast majority of graph-traversal use-cases without
external graph databases.

## Context

A recursive CTE has three parts:

1. **Anchor term** — the base rows (the root(s) of the traversal).
2. **UNION ALL** — combines the anchor with the recursive term.
3. **Recursive term** — joins the CTE back to the same table to walk one level deeper.

SQLite executes this as a breadth-first (or depth-first with ordering) iteration
until no new rows are produced. The result is the complete set of reachable nodes
from the anchor.

Supported use-cases in SQLite / D1:

| Use-case | Structure | Query pattern |
|----------|-----------|---------------|
| Tree descent | `parent_id` column | Recursive from root downward |
| Tree ascent | `parent_id` column | Recursive from leaf upward |
| Shortest path | Edge table | BFS with cycle guard |
| All ancestors | Closure table | Simple JOIN (no recursion needed) |
| Topological sort | DAG edge table | Recursive with depth tracking |

## Schema Design

### Adjacency List (most common)

```sql
-- Category tree: each node points to its parent
CREATE TABLE categories (
  id        TEXT PRIMARY KEY,
  parent_id TEXT REFERENCES categories(id),  -- NULL = root
  name      TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_categories_parent ON categories(parent_id);

-- Seed data
INSERT INTO categories VALUES
  ('root',    NULL,    'All Products', 0),
  ('elec',    'root',  'Electronics',  1),
  ('phones',  'elec',  'Phones',       1),
  ('laptops', 'elec',  'Laptops',      2),
  ('apple',   'phones','Apple',        1),
  ('android', 'phones','Android',      2),
  ('clothes', 'root',  'Clothing',     2);
```

### Edge Table (for general graphs / DAGs)

```sql
-- Directed edges for a task dependency graph
CREATE TABLE task_edges (
  from_task TEXT NOT NULL,
  to_task   TEXT NOT NULL,
  PRIMARY KEY (from_task, to_task)
);

CREATE INDEX idx_edges_to ON task_edges(to_task);
```

## Recursive Queries

### Descend a Tree — All Descendants of a Node

```sql
-- Find all subcategories under 'elec' (including itself)
WITH RECURSIVE subtree(id, name, parent_id, depth) AS (
  -- Anchor: start at the target node
  SELECT id, name, parent_id, 0 AS depth
  FROM categories
  WHERE id = 'elec'

  UNION ALL

  -- Recursive: join children to the current frontier
  SELECT c.id, c.name, c.parent_id, st.depth + 1
  FROM categories c
  JOIN subtree st ON c.parent_id = st.id
)
SELECT id, name, depth
FROM subtree
ORDER BY depth, sort_order;
-- Returns: elec(0), phones(1), laptops(1), apple(2), android(2)
```

### Ascend a Tree — All Ancestors of a Node (Breadcrumb Path)

```sql
-- Build breadcrumb: path from 'apple' up to root
WITH RECURSIVE ancestors(id, name, parent_id, level) AS (
  -- Anchor: start at the leaf
  SELECT id, name, parent_id, 0
  FROM categories
  WHERE id = 'apple'

  UNION ALL

  -- Recursive: walk upward
  SELECT c.id, c.name, c.parent_id, a.level + 1
  FROM categories c
  JOIN ancestors a ON c.id = a.parent_id
)
SELECT id, name, level
FROM ancestors
ORDER BY level DESC;   -- root first
-- Returns: root → elec → phones → apple
```

### Compute Full Path as a String

```sql
WITH RECURSIVE path(id, name, parent_id, full_path) AS (
  SELECT id, name, parent_id, name AS full_path
  FROM categories
  WHERE id = 'apple'

  UNION ALL

  SELECT c.id, c.name, c.parent_id, c.name || ' > ' || p.full_path
  FROM categories c
  JOIN path p ON c.id = p.parent_id
)
SELECT full_path
FROM path
WHERE parent_id IS NULL;
-- Result: "All Products > Electronics > Phones > Apple"
```

### Cycle Detection in a General Graph

SQLite does not automatically detect cycles. An infinite loop will exhaust memory.
Guard against cycles using an `ancestors` set stored in a text column:

```sql
WITH RECURSIVE traversal(node, visited, depth) AS (
  -- Anchor: starting node
  SELECT 'A' AS node, ',A,' AS visited, 0 AS depth

  UNION ALL

  SELECT e.to_task,
         t.visited || e.to_task || ',',
         t.depth + 1
  FROM task_edges e
  JOIN traversal t ON e.from_task = t.node
  -- Stop if we've already visited this node (cycle guard)
  WHERE t.visited NOT LIKE '%,' || e.to_task || ',%'
    AND t.depth < 50   -- hard depth limit as a safety net
)
SELECT DISTINCT node, depth
FROM traversal
ORDER BY depth;
```

### Topological Sort for a DAG

```sql
-- Given task_edges: find a valid execution order (tasks with no deps first)
WITH RECURSIVE topo(task, depth) AS (
  -- Anchor: tasks with no incoming edges (no dependencies)
  SELECT t.id, 0
  FROM tasks t
  WHERE NOT EXISTS (
    SELECT 1 FROM task_edges e WHERE e.to_task = t.id
  )

  UNION ALL

  -- Expand: tasks whose ALL dependencies are already in the traversal
  SELECT e.to_task, tp.depth + 1
  FROM task_edges e
  JOIN topo tp ON e.from_task = tp.task
)
SELECT task, MAX(depth) AS earliest_start
FROM topo
GROUP BY task
ORDER BY earliest_start;
```

### Shortest Path (BFS)

```sql
-- Find shortest path between two nodes in an undirected graph
WITH RECURSIVE bfs(node, path, steps) AS (
  SELECT 'start_node', 'start_node', 0

  UNION ALL

  SELECT e.to_task,
         b.path || ',' || e.to_task,
         b.steps + 1
  FROM task_edges e
  JOIN bfs b ON e.from_task = b.node
  WHERE b.path NOT LIKE '%' || e.to_task || '%'   -- cycle guard
    AND b.steps < 20
)
SELECT path, steps
FROM bfs
WHERE node = 'end_node'
ORDER BY steps
LIMIT 1;
```

## Integrating with D1 / Workers

```typescript
// src/services/category-service.ts
import { D1Database } from '@cloudflare/workers-types';

interface CategoryNode {
  id: string;
  name: string;
  depth: number;
}

/**
 * Returns all descendants of a given category, including the category itself.
 * Uses a recursive CTE — single round-trip to D1.
 */
export async function getSubtree(db: D1Database, rootId: string): Promise<CategoryNode[]> {
  const result = await db
    .prepare(`
      WITH RECURSIVE subtree(id, name, parent_id, depth) AS (
        SELECT id, name, parent_id, 0
        FROM categories
        WHERE id = ?
        UNION ALL
        SELECT c.id, c.name, c.parent_id, s.depth + 1
        FROM categories c
        JOIN subtree s ON c.parent_id = s.id
      )
      SELECT id, name, depth
      FROM subtree
      ORDER BY depth, name
    `)
    .bind(rootId)
    .all<CategoryNode>();

  return result.results;
}

/**
 * Returns the breadcrumb path as an ordered array from root to leaf.
 */
export async function getBreadcrumb(db: D1Database, leafId: string): Promise<CategoryNode[]> {
  const result = await db
    .prepare(`
      WITH RECURSIVE ancestors(id, name, parent_id, level) AS (
        SELECT id, name, parent_id, 0
        FROM categories
        WHERE id = ?
        UNION ALL
        SELECT c.id, c.name, c.parent_id, a.level + 1
        FROM categories c
        JOIN ancestors a ON c.id = a.parent_id
      )
      SELECT id, name, level AS depth
      FROM ancestors
      ORDER BY level DESC
    `)
    .bind(leafId)
    .all<CategoryNode>();

  return result.results;
}
```

## Performance Considerations

Recursive CTEs in SQLite process one level at a time. With deep trees (depth > 50),
performance degrades and memory use grows. Mitigation strategies:

- **Add a hard depth limit** in the WHERE clause of the recursive term.
- **Closure table**: Pre-materialize all ancestor/descendant pairs. Trades write
  complexity for O(1) descendant reads. Prefer for trees with frequent reads and
  infrequent structural changes.
- **Nested set model**: Stores `lft`/`rgt` integers. Descendants are a simple range
  query: `WHERE lft BETWEEN parent.lft AND parent.rgt`. Expensive to update on
  inserts/moves. Good for read-heavy, rarely-restructured trees.

```sql
-- Closure table: pre-computed ancestor/descendant relationships
CREATE TABLE category_closure (
  ancestor_id   TEXT NOT NULL,
  descendant_id TEXT NOT NULL,
  depth         INTEGER NOT NULL,
  PRIMARY KEY (ancestor_id, descendant_id)
);

-- All descendants of 'elec' with a single non-recursive query:
SELECT c.id, c.name, cc.depth
FROM category_closure cc
JOIN categories c ON c.id = cc.descendant_id
WHERE cc.ancestor_id = 'elec'
ORDER BY cc.depth;
```

## Anti-patterns

- **Unbounded recursion without a depth limit**: A cycle in an adjacency list table
  will cause the D1 query to run until it hits SQLite's default recursion limit
  (1 000 iterations by default) or the Worker CPU time limit. Always set
  `PRAGMA max_page_count` and include a depth cap.
- **Using recursion for flat lookups**: If all you need is direct children
  (`WHERE parent_id = ?`), a recursive CTE is overkill and slower.
- **Storing the full path in a VARCHAR**: Path enumeration columns (e.g. `/a/b/c`)
  work for simple cases but break on renames. Use a proper adjacency list plus
  the CTE approach.
- **Fetching the full tree and filtering in JS**: Pulling 50 000 nodes to the Worker
  and filtering in-memory is 100× slower than a WHERE clause on an indexed column.

## Gotchas

- SQLite's recursive CTE default recursion depth is 1 000. For deeper trees,
  set `PRAGMA recursive_triggers = ON` but be aware D1 may not expose all PRAGMAs.
- `UNION ALL` is required (not `UNION`) for performance. `UNION` would de-duplicate
  on every iteration, which is both slow and incorrect for depth-tracking queries.
- The `visited` text-column cycle guard (`NOT LIKE '%,node,%'`) is O(n) per edge.
  For large graphs, materialize visited nodes in a temp table if SQLite supports it,
  or fall back to application-side BFS.
- D1's query size limit (currently 100 KB for the SQL text) rarely affects recursive
  CTEs, but extremely long dynamic queries with inlined node lists may hit it.

## Verification

```sql
-- Verify descendant count for known tree
WITH RECURSIVE subtree(id) AS (
  SELECT 'root'
  UNION ALL
  SELECT c.id FROM categories c JOIN subtree s ON c.parent_id = s.id
)
SELECT COUNT(*) AS total_nodes FROM subtree;
-- Should equal total rows in categories table for a connected tree

-- Verify no cycles exist in adjacency list
WITH RECURSIVE check_cycle(id, visited) AS (
  SELECT id, ',' || id || ',' FROM categories WHERE parent_id IS NULL
  UNION ALL
  SELECT c.id, cc.visited || c.id || ','
  FROM categories c
  JOIN check_cycle cc ON c.parent_id = cc.id
  WHERE cc.visited NOT LIKE '%,' || c.id || ',%'
)
SELECT COUNT(*) AS reachable FROM check_cycle;
-- If reachable < total rows, there are unreachable nodes (possible cycle)
```

## Related

- `cte-common-table-expressions.md` — general CTE usage patterns
- `d1-sqlite-query-optimization.md` — EXPLAIN QUERY PLAN for D1
- `hierarchical-data-ltree.md` — PostgreSQL ltree extension for tree paths
- `graph-database-neo4j.md` — when a dedicated graph DB is worth the complexity
- `sqlite-journal-modes.md` — SQLite runtime configuration for D1

## Sources

- SQLite WITH clause documentation: sqlite.org/lang_with.html
- SQLite recursive CTE examples: sqlite.org/lang_with.html#recursive_common_table_expressions
- Cloudflare D1 SQL API: developers.cloudflare.com/d1/worker-api
