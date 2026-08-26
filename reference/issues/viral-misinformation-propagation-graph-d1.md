# Viral Misinformation Propagation Graph With D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

On example project, a piece of misinformation can spread through anonymous reposts and quote-posts before any moderator sees it. By the time a first report arrives, the content may have propagated across hundreds of threads, making takedown laborious. The platform needs a propagation graph that tracks how content spreads from origin to leaf nodes, enabling targeted takedown of the entire tree rather than leaf-by-leaf removal, and fast identification of the most influential amplification nodes.

## Context

Because example project is anonymous and ephemeral, the propagation graph is built from content relationships (repost-of, quote-of, reply-to) rather than account relationships. D1 stores the adjacency list; Workers traverse it on-demand for takedown operations. The graph is small enough per content item that a recursive common-table expression (CTE) in D1 can retrieve the full propagation tree in a single query, avoiding multi-round-trip graph traversals.

## Detection — Propagation Graph Construction in D1

Every repost and quote-post records an edge in the `content_edges` table. A scheduled Worker identifies content items whose propagation velocity (new edges per minute) spikes above threshold.

```typescript
// workers/propagation-ingest.ts
export interface Env {
  DB: D1Database;
}

export interface ContentEdge {
  childId: string;
  parentId: string;
  edgeType: "repost" | "quote" | "reply";
  sessionId: string;
}

export async function recordContentEdge(
  db: D1Database,
  edge: ContentEdge
): Promise<void> {
  // Upsert the child content node
  await db.prepare(
    `INSERT INTO content_nodes (content_id, created_at)
     VALUES (?, datetime('now'))
     ON CONFLICT(content_id) DO NOTHING`
  ).bind(edge.childId).run();

  // Record the propagation edge
  await db.prepare(
    `INSERT INTO content_edges (child_id, parent_id, edge_type, session_id, created_at)
     VALUES (?, ?, ?, ?, datetime('now'))
     ON CONFLICT(child_id, parent_id) DO NOTHING`
  ).bind(edge.childId, edge.parentId, edge.edgeType, edge.sessionId).run();
}

export async function getVelocitySpikes(
  db: D1Database,
  windowMinutes: number = 5,
  threshold: number = 20
): Promise<Array<{ rootId: string; edgeCount: number }>> {
  // Find content trees growing too fast: >threshold new edges in windowMinutes
  const { results } = await db.prepare(`
    WITH RECURSIVE tree(root_id, node_id) AS (
      -- seed: all edges created recently
      SELECT parent_id AS root_id, child_id AS node_id
      FROM content_edges
      WHERE created_at > datetime('now', '-' || ? || ' minutes')
      UNION
      -- walk up to find root
      SELECT t.root_id, e.parent_id
      FROM tree t
      JOIN content_edges e ON e.child_id = t.root_id
    )
    SELECT root_id, COUNT(*) AS edge_count
    FROM tree
    WHERE root_id NOT IN (SELECT child_id FROM content_edges)  -- only true roots
    GROUP BY root_id
    HAVING edge_count > ?
    ORDER BY edge_count DESC
    LIMIT 20
  `).bind(windowMinutes, threshold).all<{ root_id: string; edge_count: number }>();

  return results.map(r => ({ rootId: r.root_id, edgeCount: r.edge_count }));
}
```

## Enforcement — Full Tree Retrieval and Takedown

When a moderator confirms content as misinformation, the entire propagation tree is retrieved with a single recursive CTE and all nodes are marked for takedown in one D1 batch.

```typescript
// workers/misinformation-takedown.ts
export interface Env {
  DB: D1Database;
}

export async function takedownPropagationTree(
  db: D1Database,
  rootId: string,
  moderatorId: string,
  reason: string
): Promise<{ totalRemoved: number; treeDepth: number }> {
  // Retrieve the full tree using recursive CTE
  const { results: treeNodes } = await db.prepare(`
    WITH RECURSIVE propagation(content_id, depth) AS (
      SELECT ?, 0
      UNION ALL
      SELECT e.child_id, p.depth + 1
      FROM content_edges e
      JOIN propagation p ON e.parent_id = p.content_id
      WHERE p.depth < 50  -- safety limit
    )
    SELECT content_id, MAX(depth) AS depth
    FROM propagation
    GROUP BY content_id
  `).bind(rootId).all<{ content_id: string; depth: number }>();

  if (treeNodes.length === 0) return { totalRemoved: 0, treeDepth: 0 };

  const maxDepth = Math.max(...treeNodes.map(n => n.depth));
  const contentIds = treeNodes.map(n => n.content_id);

  // Batch mark all nodes as removed (D1 supports up to 100 statements per batch)
  const batchSize = 50;
  for (let i = 0; i < contentIds.length; i += batchSize) {
    const chunk = contentIds.slice(i, i + batchSize);
    const placeholders = chunk.map(() => "?").join(", ");
    await db.prepare(
      `UPDATE content_nodes
       SET removed = 1, removed_at = datetime('now'), removal_reason = ?, removed_by = ?
       WHERE content_id IN (${placeholders})`
    ).bind(reason, moderatorId, ...chunk).run();
  }

  // Record the takedown event
  await db.prepare(
    `INSERT INTO takedown_events
       (root_id, node_count, max_depth, reason, moderator_id, taken_down_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))`
  ).bind(rootId, treeNodes.length, maxDepth, reason, moderatorId).run();

  return { totalRemoved: treeNodes.length, treeDepth: maxDepth };
}
```

## Escalation — Amplification Node Identification

Some anonymous sessions are disproportionate amplifiers — their reposts reliably go viral. Identifying and soft-limiting these nodes slows future misinformation spread even before content is flagged.

```typescript
// workers/amplifier-detection.ts
export async function findTopAmplifiers(
  db: D1Database,
  lookbackDays: number = 7,
  minSpread: number = 10
): Promise<Array<{ sessionId: string; spreadScore: number }>> {
  const { results } = await db.prepare(`
    SELECT
      e.session_id,
      COUNT(DISTINCT e.child_id) AS reposts_made,
      MAX(sub.descendants) AS max_spread
    FROM content_edges e
    JOIN (
      WITH RECURSIVE tree(root_id, child_id) AS (
        SELECT parent_id, child_id FROM content_edges
        UNION ALL
        SELECT t.root_id, e2.child_id
        FROM tree t JOIN content_edges e2 ON e2.parent_id = t.child_id
        WHERE (SELECT COUNT(*) FROM tree) < 10000
      )
      SELECT root_id, COUNT(*) AS descendants FROM tree GROUP BY root_id
    ) sub ON sub.root_id = e.child_id
    WHERE e.created_at > datetime('now', '-' || ? || ' days')
    GROUP BY e.session_id
    HAVING max_spread >= ?
    ORDER BY max_spread DESC
    LIMIT 50
  `).bind(lookbackDays, minSpread).all<{
    session_id: string;
    reposts_made: number;
    max_spread: number;
  }>();

  return results.map(r => ({
    sessionId: r.session_id,
    spreadScore: r.max_spread * r.reposts_made,
  }));
}

export async function applySoftLimitToAmplifiers(
  db: D1Database,
  sessionIds: string[]
): Promise<void> {
  const placeholders = sessionIds.map(() => "(?, 'amplifier-limit', datetime('now', '+48 hours'))").join(", ");
  await db.prepare(
    `INSERT INTO session_restrictions (session_id, restriction, expires_at)
     VALUES ${placeholders}
     ON CONFLICT(session_id) DO UPDATE SET restriction = 'amplifier-limit', expires_at = excluded.expires_at`
  ).bind(...sessionIds).run();
}
```

## Monitoring — Graph Metrics Dashboard

```typescript
// D1 queries for operations dashboard
const PROPAGATION_SUMMARY = `
  SELECT
    DATE(e.created_at) AS day,
    COUNT(DISTINCT e.parent_id) AS unique_roots,
    COUNT(*) AS total_edges,
    MAX(sub.depth) AS max_tree_depth
  FROM content_edges e
  LEFT JOIN (
    WITH RECURSIVE tree(root_id, child_id, depth) AS (
      SELECT parent_id, child_id, 1 FROM content_edges
      UNION ALL
      SELECT t.root_id, e2.child_id, t.depth + 1
      FROM tree t JOIN content_edges e2 ON e2.parent_id = t.child_id
      WHERE t.depth < 20
    )
    SELECT root_id, MAX(depth) AS depth FROM tree GROUP BY root_id
  ) sub ON sub.root_id = e.parent_id
  WHERE e.created_at > datetime('now', '-7 days')
  GROUP BY day
  ORDER BY day DESC
`;
```

## Anti-patterns

- Storing the graph as a nested JSON blob per post — makes tree traversal O(n) reads instead of one CTE
- Removing only the leaf nodes on a takedown — root and intermediate nodes remain discoverable via direct URL
- Running the recursive CTE without a depth guard (`WHERE depth < N`) — can cause SQLite to loop indefinitely on cycles introduced by quote-posts that reference each other
- Identifying amplifiers only at takedown time — by then, the amplifier has already spread content to other trees

## Gotchas

- D1's SQLite dialect supports recursive CTEs but has a default recursion depth limit; test with deeply nested trees (>20 levels)
- `ON CONFLICT DO NOTHING` in `content_edges` requires a UNIQUE constraint on `(child_id, parent_id)` — add this in migrations
- D1 batch statements share a single transaction; a failure in any statement rolls back the entire batch — check `meta.success` on each result
- The propagation velocity query can be slow on large `content_edges` tables without an index on `created_at` and `parent_id`; add composite index `(created_at, parent_id)`
- The amplifier subquery joins a recursive CTE against another table — this is valid in SQLite 3.35+ but ensure D1's SQLite version supports it

## Verification

1. Insert a root post and a chain of 5 reposts via `recordContentEdge`.
2. Call `getVelocitySpikes(db, 60, 3)` — expect the root post to appear.
3. Call `takedownPropagationTree(db, rootId, "mod1", "misinformation")` — expect `totalRemoved = 6`, `treeDepth = 5`.
4. Query `content_nodes WHERE removed = 1` — all 6 nodes should be present.
5. Insert a session that reposts 5 different posts each spreading to 15 children — `findTopAmplifiers` should surface that session.

## Related

- `/documentation/categories/issues/misinformation-labeling-pipeline-ugc.md`
- `/documentation/categories/issues/election-misinformation-detection-workers-ai.md`
- `/documentation/categories/issues/viral-misinformation-spread-containment-workers-queues.md`
- `/documentation/categories/issues/emergency-content-takedown-circuit-breaker-queues.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/lang_with.html (SQLite recursive CTE)
- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://www.cs.cornell.edu/path/to/project (network propagation models)
