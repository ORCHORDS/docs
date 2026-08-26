# Hierarchical Data with Closure Table in D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have hierarchical data — a product category tree, an org chart, nested comments — stored in D1. You need efficient queries for: "fetch entire subtree of node X", "fetch all ancestors of node Y", and "move a subtree". Naive adjacency lists (single `parent_id` column) require recursive CTEs that are slow on large trees or many levels.

## Context

The closure table pattern maintains a separate table with one row for every ancestor–descendant pair in the tree (including self-references at depth 0). This trades write complexity for very fast reads with a simple join. It is especially well-suited to D1 because all reads are single SQL statements with no application-side recursion.

---

## Schema

```sql
-- The actual entity table (categories, comments, org nodes, …)
CREATE TABLE IF NOT EXISTS categories (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT    NOT NULL,
  description TEXT
);

-- Closure table: every (ancestor, descendant) pair with path length
CREATE TABLE IF NOT EXISTS category_closure (
  ancestor_id   INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  descendant_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  depth         INTEGER NOT NULL,          -- 0 = self, 1 = parent, 2 = grandparent …
  PRIMARY KEY (ancestor_id, descendant_id)
);

CREATE INDEX IF NOT EXISTS idx_closure_desc  ON category_closure(descendant_id);
CREATE INDEX IF NOT EXISTS idx_closure_depth ON category_closure(depth);
```

---

## Inserting a New Node

When adding a node, copy all closure rows from the parent's ancestors and add a self-reference.

```typescript
// src/closure.ts
import type { D1Database } from '@cloudflare/workers-types';

export async function insertNode(
  db: D1Database,
  name: string,
  description: string | null,
  parentId: number | null   // null = root node
): Promise<number> {
  // Insert the entity row
  const { meta } = await db
    .prepare('INSERT INTO categories (name, description) VALUES (?, ?)')
    .bind(name, description ?? null)
    .run();
  const newId = meta.last_row_id as number;

  const stmts = [
    // Self-reference (depth 0)
    db.prepare(
      'INSERT INTO category_closure (ancestor_id, descendant_id, depth) VALUES (?, ?, 0)'
    ).bind(newId, newId),
  ];

  if (parentId !== null) {
    // Copy all ancestor rows of the parent, incrementing depth by 1
    stmts.push(
      db.prepare(
        `INSERT INTO category_closure (ancestor_id, descendant_id, depth)
         SELECT ancestor_id, ?, depth + 1
         FROM category_closure
         WHERE descendant_id = ?`
      ).bind(newId, parentId)
    );
  }

  await db.batch(stmts);
  return newId;
}
```

---

## Querying Subtrees and Ancestors

```typescript
// src/closure.ts (continued)

export interface CategoryRow {
  id:          number;
  name:        string;
  description: string | null;
  depth:       number;
}

/** Return the entire subtree rooted at `nodeId`, ordered by depth then name. */
export async function getSubtree(
  db: D1Database,
  nodeId: number
): Promise<CategoryRow[]> {
  const { results } = await db
    .prepare(
      `SELECT c.id, c.name, c.description, cl.depth
       FROM category_closure cl
       JOIN categories c ON c.id = cl.descendant_id
       WHERE cl.ancestor_id = ?
       ORDER BY cl.depth, c.name`
    )
    .bind(nodeId)
    .all<CategoryRow>();
  return results;
}

/** Return the direct children of `nodeId` only (depth = 1). */
export async function getChildren(
  db: D1Database,
  nodeId: number
): Promise<CategoryRow[]> {
  const { results } = await db
    .prepare(
      `SELECT c.id, c.name, c.description, cl.depth
       FROM category_closure cl
       JOIN categories c ON c.id = cl.descendant_id
       WHERE cl.ancestor_id = ? AND cl.depth = 1
       ORDER BY c.name`
    )
    .bind(nodeId)
    .all<CategoryRow>();
  return results;
}

/** Return all ancestors of `nodeId` (excluding self), nearest first. */
export async function getAncestors(
  db: D1Database,
  nodeId: number
): Promise<CategoryRow[]> {
  const { results } = await db
    .prepare(
      `SELECT c.id, c.name, c.description, cl.depth
       FROM category_closure cl
       JOIN categories c ON c.id = cl.ancestor_id
       WHERE cl.descendant_id = ? AND cl.depth > 0
       ORDER BY cl.depth`
    )
    .bind(nodeId)
    .all<CategoryRow>();
  return results;
}

/** Return the immediate parent (depth = 1 ancestor), or null for root. */
export async function getParent(
  db: D1Database,
  nodeId: number
): Promise<CategoryRow | null> {
  const row = await db
    .prepare(
      `SELECT c.id, c.name, c.description, cl.depth
       FROM category_closure cl
       JOIN categories c ON c.id = cl.ancestor_id
       WHERE cl.descendant_id = ? AND cl.depth = 1`
    )
    .bind(nodeId)
    .first<CategoryRow>();
  return row ?? null;
}
```

---

## Deleting a Node (and Its Subtree)

With `ON DELETE CASCADE` on `category_closure.descendant_id`, deleting the entity row cascades automatically. To delete only the node and re-parent its children, first move the children:

```typescript
// src/closure.ts (continued)

/** Delete a leaf node. Throws if the node has children. */
export async function deleteLeaf(
  db: D1Database,
  nodeId: number
): Promise<void> {
  const children = await getChildren(db, nodeId);
  if (children.length > 0) {
    throw new Error(`Node ${nodeId} has ${children.length} children; cannot delete.`);
  }
  // Cascade handles closure rows via FK
  await db.prepare('DELETE FROM categories WHERE id = ?').bind(nodeId).run();
}

/**
 * Delete an entire subtree rooted at `nodeId`.
 * Deletes in reverse depth order to respect FK constraints if CASCADE is off.
 */
export async function deleteSubtree(
  db: D1Database,
  nodeId: number
): Promise<void> {
  // Collect all descendant IDs (deepest first)
  const { results } = await db
    .prepare(
      `SELECT descendant_id FROM category_closure
       WHERE ancestor_id = ?
       ORDER BY depth DESC`
    )
    .bind(nodeId)
    .all<{ descendant_id: number }>();

  const stmts = results.map(({ descendant_id }) =>
    db.prepare('DELETE FROM categories WHERE id = ?').bind(descendant_id)
  );
  await db.batch(stmts);
}
```

---

## Worker Handler

```typescript
// src/worker.ts
import { insertNode, getSubtree, getAncestors, deleteLeaf } from './closure';

export interface Env { DB: D1Database; }

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url  = new URL(req.url);
    const path = url.pathname;

    if (path === '/subtree') {
      const id = Number(url.searchParams.get('id'));
      return Response.json(await getSubtree(env.DB, id));
    }

    if (path === '/ancestors') {
      const id = Number(url.searchParams.get('id'));
      return Response.json(await getAncestors(env.DB, id));
    }

    if (path === '/node' && req.method === 'POST') {
      const { name, description, parentId } = await req.json<{
        name: string;
        description?: string;
        parentId?: number;
      }>();
      const newId = await insertNode(env.DB, name, description ?? null, parentId ?? null);
      return Response.json({ id: newId }, { status: 201 });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Anti-patterns

- **Recursive CTE for deep trees** — `WITH RECURSIVE` in SQLite works but becomes slow past ~15 levels; closure table reads are O(1) SQL.
- **Storing only `parent_id`** — forces application-side recursion or slow CTEs for subtree queries.
- **Deleting closure rows manually** — rely on `ON DELETE CASCADE` on both FK columns to keep closure consistent.

---

## Gotchas

- The closure table grows as O(N × average depth). For very deep trees (> 50 levels) with millions of nodes, storage can be significant. Materialise only the top K levels of closure for deep taxonomies.
- Moving a subtree requires: (1) delete all closure rows where ancestor is outside the subtree and descendant is inside; (2) re-insert from the new parent's ancestors. This is a multi-step operation — wrap in a batch.
- D1's `meta.last_row_id` is only reliable for `INSERT` statements; check `meta.changes` to confirm a row was inserted.

---

## Verification

```bash
# Seed a small tree: Root(1) → Electronics(2) → Phones(3), Tablets(4)
wrangler d1 execute MY_DB --command "
  INSERT INTO categories VALUES (1,'Root',NULL),(2,'Electronics',NULL),(3,'Phones',NULL),(4,'Tablets',NULL);
  INSERT INTO category_closure VALUES
    (1,1,0),(2,2,0),(3,3,0),(4,4,0),
    (1,2,1),(1,3,2),(1,4,2),
    (2,3,1),(2,4,1);
"

# Subtree of Electronics (id=2): should return Electronics, Phones, Tablets
curl 'https://my-worker.example.com/subtree?id=2'

# Ancestors of Phones (id=3): should return Electronics(depth=1), Root(depth=2)
curl 'https://my-worker.example.com/ancestors?id=3'
```

---

## Related

- `d1-graph-adjacency-list-workers.md` — general graph traversal
- `d1-optimistic-locking-version-column.md` — safe concurrent tree mutations
- Bill Karwin, *SQL Antipatterns*, ch. 3 — Naive Trees

## Sources

- Closure table pattern: https://www.slideshare.net/billkarwin/models-for-hierarchical-data
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
