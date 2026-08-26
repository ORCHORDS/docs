# D1 Adjacency List Hierarchical Data Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to store tree-structured data — categories, org charts, nested comments, folder hierarchies — in D1. Queries like "give me all ancestors of node X" or "give me the full subtree under node Y" either require multiple round-trips from the Worker or a recursive CTE that becomes hard to maintain as depth grows.

## Context

The **adjacency list** model stores each node with a single `parent_id` foreign key pointing to its parent. It is the simplest tree representation for insert and update, and SQLite (D1) supports it natively. For read-heavy subtree traversal, pair it with a **closure table** — a separate table holding every ancestor–descendant pair — to turn multi-level fetches into a single indexed join. D1's SQLite engine supports recursive CTEs, but closure tables offer predictable query plans and no recursion depth limits.

## Schema: Adjacency List with Closure Table

```sql
-- Core nodes table
CREATE TABLE categories (
  id       INTEGER PRIMARY KEY,
  name     TEXT    NOT NULL,
  parent_id INTEGER REFERENCES categories(id) ON DELETE CASCADE
);

-- Closure table: one row per (ancestor, descendant) pair including self
CREATE TABLE category_closure (
  ancestor_id   INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  descendant_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  depth         INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ancestor_id, descendant_id)
);

CREATE INDEX idx_closure_descendant ON category_closure(descendant_id);
```

## Inserting a Node

When inserting a new node, copy all closure rows for the parent and add a self-reference row in a single batch.

```typescript
// src/tree.ts
export async function insertNode(
  db: D1Database,
  name: string,
  parentId: number | null
): Promise<number> {
  const { meta } = await db
    .prepare('INSERT INTO categories (name, parent_id) VALUES (?, ?)')
    .bind(name, parentId)
    .run();
  const newId = meta.last_row_id as number;

  if (parentId === null) {
    // Root node — only self-reference
    await db
      .prepare('INSERT INTO category_closure (ancestor_id, descendant_id, depth) VALUES (?, ?, 0)')
      .bind(newId, newId)
      .run();
  } else {
    // Copy parent's ancestors and add self-reference
    await db.batch([
      db.prepare(`
        INSERT INTO category_closure (ancestor_id, descendant_id, depth)
        SELECT ancestor_id, ?, depth + 1
        FROM category_closure
        WHERE descendant_id = ?
      `).bind(newId, parentId),
      db.prepare(
        'INSERT INTO category_closure (ancestor_id, descendant_id, depth) VALUES (?, ?, 0)'
      ).bind(newId, newId),
    ]);
  }
  return newId;
}
```

## Fetching a Full Subtree

```typescript
export interface CategoryNode {
  id: number;
  name: string;
  parent_id: number | null;
  depth: number;
}

export async function getSubtree(
  db: D1Database,
  rootId: number
): Promise<CategoryNode[]> {
  const { results } = await db
    .prepare(`
      SELECT c.id, c.name, c.parent_id, cl.depth
      FROM category_closure cl
      JOIN categories c ON c.id = cl.descendant_id
      WHERE cl.ancestor_id = ?
      ORDER BY cl.depth, c.name
    `)
    .bind(rootId)
    .all<CategoryNode>();
  return results;
}
```

## Fetching All Ancestors (Breadcrumb Path)

```typescript
export async function getAncestors(
  db: D1Database,
  nodeId: number
): Promise<CategoryNode[]> {
  const { results } = await db
    .prepare(`
      SELECT c.id, c.name, c.parent_id, cl.depth
      FROM category_closure cl
      JOIN categories c ON c.id = cl.ancestor_id
      WHERE cl.descendant_id = ?
      ORDER BY cl.depth DESC  -- root first
    `)
    .bind(nodeId)
    .all<CategoryNode>();
  return results;
}
```

## Moving a Subtree

Moving a node requires deleting the old closure rows for the subtree and re-inserting them under the new parent.

```typescript
export async function moveNode(
  db: D1Database,
  nodeId: number,
  newParentId: number
): Promise<void> {
  await db.batch([
    // 1. Delete all ancestor links for the subtree (keep self-links)
    db.prepare(`
      DELETE FROM category_closure
      WHERE descendant_id IN (
        SELECT descendant_id FROM category_closure WHERE ancestor_id = ?
      )
      AND ancestor_id NOT IN (
        SELECT descendant_id FROM category_closure WHERE ancestor_id = ?
      )
    `).bind(nodeId, nodeId),

    // 2. Reattach subtree under new parent
    db.prepare(`
      INSERT INTO category_closure (ancestor_id, descendant_id, depth)
      SELECT supertree.ancestor_id, subtree.descendant_id,
             supertree.depth + subtree.depth + 1
      FROM category_closure subtree
      JOIN category_closure supertree ON supertree.descendant_id = ?
      WHERE subtree.ancestor_id = ?
    `).bind(newParentId, nodeId),

    // 3. Update parent_id on the node itself
    db.prepare('UPDATE categories SET parent_id = ? WHERE id = ?')
      .bind(newParentId, nodeId),
  ]);
}
```

## Anti-patterns

- **Walking the adjacency list row-by-row from the Worker**: issuing one query per level creates N round-trips over the network. Use the closure table or a recursive CTE instead.
- **Storing a `path` string like `/1/4/7/`**: requires string manipulation and breaks on renames; the closure table is strictly more capable.
- **Skipping the closure table for "shallow" trees**: trees grow. A two-level tree becoming five levels later means a schema migration. Start with the closure table.

## Gotchas

- **Deleting a node** with `ON DELETE CASCADE` on `category_closure.ancestor_id` and `descendant_id` handles cleanup automatically, but verify your D1 migration enables foreign keys: `PRAGMA foreign_keys = ON` must be set per connection. D1 enables foreign keys by default, but confirm with `PRAGMA foreign_keys`.
- **`last_row_id`** is available on `.run()` result `meta`, not on `.all()` or `.first()`.
- The closure table grows as O(depth × nodes). For very deep trees (>50 levels) with millions of nodes, consider a path-enumeration or nested set model instead.
- `db.batch()` wraps all statements in an implicit transaction on D1, so the insert + closure copy is atomic.

## Verification

```typescript
// Smoke test: insert root → child → grandchild, verify path
const rootId = await insertNode(db, 'Electronics', null);
const laptopsId = await insertNode(db, 'Laptops', rootId);
const gamingId = await insertNode(db, 'Gaming Laptops', laptopsId);

const ancestors = await getAncestors(db, gamingId);
console.assert(ancestors.length === 3, 'should have 3 levels including self');
console.assert(ancestors[0].id === rootId, 'root first');

const subtree = await getSubtree(db, rootId);
console.assert(subtree.length === 3, 'subtree should contain all 3 nodes');
```

## Related

- `d1-recursive-cte-hierarchical-data-workers.md` — same tree problem solved with `WITH RECURSIVE`
- `d1-foreign-key-on-delete-cascade-workers.md`
- `d1-batch-operations-performance.md`

## Sources

- SQLite closure table pattern: Joe Celko, *SQL for Smarties*, ch. 29
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite foreign key docs: https://www.sqlite.org/foreignkeys.html
