# Graph Data in D1 Using Adjacency List

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to model graph-like relationships (social follows, dependency trees, road networks) inside Cloudflare D1 without an external graph database. Queries like "find all nodes reachable from X" or "what is the shortest path between A and B" must run inside a Workers handler.

## Context

D1 is SQLite-compatible. SQLite has no native graph primitives, but an adjacency list table — one row per directed edge — is sufficient for most graph workloads when BFS/DFS logic lives in the Worker. For sparse graphs with up to ~1 M edges, this pattern is fast enough for interactive use (< 50 ms) when node IDs are indexed.

---

## Schema

```sql
-- nodes table (optional, store metadata here)
CREATE TABLE IF NOT EXISTS nodes (
  id      INTEGER PRIMARY KEY,
  label   TEXT    NOT NULL,
  meta    TEXT    -- JSON blob for arbitrary properties
);

-- edges: directed adjacency list
CREATE TABLE IF NOT EXISTS edges (
  from_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  to_id   INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  weight  REAL    NOT NULL DEFAULT 1.0,
  PRIMARY KEY (from_id, to_id)
);

CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);
```

For undirected graphs, insert both `(A→B)` and `(B→A)` rows, or query `from_id = ? OR to_id = ?`.

---

## BFS / DFS in Workers TypeScript

```typescript
// src/graph.ts
import type { D1Database } from '@cloudflare/workers-types';

interface Edge {
  to_id: number;
  weight: number;
}

/** Return direct neighbours of `nodeId` */
async function neighbours(db: D1Database, nodeId: number): Promise<Edge[]> {
  const { results } = await db
    .prepare('SELECT to_id, weight FROM edges WHERE from_id = ?')
    .bind(nodeId)
    .all<Edge>();
  return results;
}

/** BFS — returns all node IDs reachable from `start` (inclusive) */
export async function bfs(
  db: D1Database,
  start: number,
  maxDepth = 10
): Promise<number[]> {
  const visited = new Set<number>([start]);
  const queue: Array<{ id: number; depth: number }> = [{ id: start, depth: 0 }];
  const order: number[] = [start];

  while (queue.length > 0) {
    const { id, depth } = queue.shift()!;
    if (depth >= maxDepth) continue;

    const nbrs = await neighbours(db, id);
    for (const { to_id } of nbrs) {
      if (!visited.has(to_id)) {
        visited.add(to_id);
        order.push(to_id);
        queue.push({ id: to_id, depth: depth + 1 });
      }
    }
  }
  return order;
}

/** DFS — iterative to avoid stack overflow on deep graphs */
export async function dfs(
  db: D1Database,
  start: number,
  maxDepth = 10
): Promise<number[]> {
  const visited = new Set<number>();
  const stack: Array<{ id: number; depth: number }> = [{ id: start, depth: 0 }];
  const order: number[] = [];

  while (stack.length > 0) {
    const { id, depth } = stack.pop()!;
    if (visited.has(id) || depth > maxDepth) continue;
    visited.add(id);
    order.push(id);

    const nbrs = await neighbours(db, id);
    for (const { to_id } of nbrs) {
      if (!visited.has(to_id)) {
        stack.push({ id: to_id, depth: depth + 1 });
      }
    }
  }
  return order;
}
```

---

## Shortest Path (Dijkstra)

```typescript
// src/graph.ts (continued)

interface PathResult {
  path: number[];
  cost: number;
}

/** Dijkstra shortest path. Returns null if no path exists. */
export async function shortestPath(
  db: D1Database,
  start: number,
  end: number
): Promise<PathResult | null> {
  // dist map: nodeId → { cost, prev }
  const dist = new Map<number, { cost: number; prev: number | null }>();
  dist.set(start, { cost: 0, prev: null });

  // Simple priority queue using a sorted array (fine for < 10k nodes)
  const pq: Array<{ id: number; cost: number }> = [{ id: start, cost: 0 }];
  const visited = new Set<number>();

  while (pq.length > 0) {
    // Pop minimum cost node
    pq.sort((a, b) => a.cost - b.cost);
    const { id, cost } = pq.shift()!;

    if (visited.has(id)) continue;
    visited.add(id);

    if (id === end) break;

    const nbrs = await neighbours(db, id);
    for (const { to_id, weight } of nbrs) {
      if (visited.has(to_id)) continue;
      const newCost = cost + weight;
      const existing = dist.get(to_id);
      if (!existing || newCost < existing.cost) {
        dist.set(to_id, { cost: newCost, prev: id });
        pq.push({ id: to_id, cost: newCost });
      }
    }
  }

  if (!dist.has(end)) return null;

  // Reconstruct path
  const path: number[] = [];
  let cur: number | null = end;
  while (cur !== null) {
    path.unshift(cur);
    cur = dist.get(cur)!.prev;
  }
  return { path, cost: dist.get(end)!.cost };
}
```

---

## Cycle Detection

```typescript
// src/graph.ts (continued)

/** Detect if there is any cycle reachable from `start`. */
export async function hasCycle(
  db: D1Database,
  start: number,
  maxNodes = 500
): Promise<boolean> {
  // DFS with grey/black colouring
  const WHITE = 0, GREY = 1, BLACK = 2;
  const colour = new Map<number, number>();
  const stack: number[] = [start];

  while (stack.length > 0) {
    const id = stack[stack.length - 1];

    if (!colour.has(id)) {
      colour.set(id, GREY);
      if (colour.size > maxNodes) return false; // give up, graph too large

      const nbrs = await neighbours(db, id);
      let pushed = false;
      for (const { to_id } of nbrs) {
        if (colour.get(to_id) === GREY) return true; // back edge = cycle
        if (!colour.has(to_id)) {
          stack.push(to_id);
          pushed = true;
          break; // process one at a time
        }
      }
      if (!pushed) {
        colour.set(id, BLACK);
        stack.pop();
      }
    } else {
      colour.set(id, BLACK);
      stack.pop();
    }
  }
  return false;
}
```

---

## Worker Handler

```typescript
// src/worker.ts
import { bfs, shortestPath, hasCycle } from './graph';

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const path = url.pathname;

    if (path === '/bfs') {
      const start = Number(url.searchParams.get('start') ?? 1);
      const depth = Number(url.searchParams.get('depth') ?? 6);
      const nodes = await bfs(env.DB, start, depth);
      return Response.json({ nodes });
    }

    if (path === '/shortest') {
      const from = Number(url.searchParams.get('from'));
      const to   = Number(url.searchParams.get('to'));
      const result = await shortestPath(env.DB, from, to);
      return Response.json(result ?? { error: 'no path' }, {
        status: result ? 200 : 404,
      });
    }

    if (path === '/cycle') {
      const start = Number(url.searchParams.get('start') ?? 1);
      const cycle = await hasCycle(env.DB, start);
      return Response.json({ cycle });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Anti-patterns

- **Recursive CTEs for BFS** — D1's SQLite supports `WITH RECURSIVE`, but for large graphs the single SQL call can time out inside a Worker (50 ms CPU limit). Move traversal logic to TypeScript.
- **Loading all edges into memory** — fetch neighbours lazily per node, not `SELECT * FROM edges` upfront.
- **Unbounded traversal** — always pass `maxDepth` to BFS/DFS to prevent infinite loops on cyclic graphs.

---

## Gotchas

- Each `neighbours()` call is a separate D1 round-trip (~1–2 ms). For graphs with branching factor > 20 and depth > 4, batch neighbour lookups: `WHERE from_id IN (?,?,?)`.
- D1 does not enforce `REFERENCES` constraints by default — run `PRAGMA foreign_keys = ON;` at migration time or in a startup query.
- `weight` must be non-negative for Dijkstra to be correct; validate on insert.

---

## Verification

```bash
# Seed a tiny graph: 1→2 (w=1), 1→3 (w=4), 2→3 (w=2), 3→4 (w=1)
wrangler d1 execute MY_DB --command "
  INSERT INTO nodes VALUES (1,'A',NULL),(2,'B',NULL),(3,'C',NULL),(4,'D',NULL);
  INSERT INTO edges VALUES (1,2,1),(1,3,4),(2,3,2),(3,4,1);
"

# Shortest path 1→4 should be [1,2,3,4] cost=4
curl 'https://my-worker.example.com/shortest?from=1&to=4'
# {"path":[1,2,3,4],"cost":4}

# BFS from 1
curl 'https://my-worker.example.com/bfs?start=1&depth=5'
# {"nodes":[1,2,3,4]}
```

---

## Related

- `d1-hierarchical-closure-table.md` — tree-specific queries with closure table
- `d1-optimistic-locking-version-column.md` — safe concurrent edge mutations
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/

## Sources

- SQLite adjacency list pattern: https://www.sqlite.org/lang_with.html
- Dijkstra reference: CLRS Introduction to Algorithms, ch. 24
