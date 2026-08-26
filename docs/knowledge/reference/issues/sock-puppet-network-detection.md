# Sock Puppet Network Detection

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

example project moderators notice clusters of anonymous accounts that always like, reply to, or boost the same content within seconds of each other, yet show no organic variation in behaviour. When one account posts, a fixed set of others amplifies it immediately. Individually each account looks normal; the suspicion only surfaces when the interaction graph is examined. Classic rate-limit and spam filters miss these actors because each account operates within per-account thresholds.

## Context

Sock puppet networks manipulate platform discourse by creating artificial consensus. On an anonymous platform there is no email or phone number to pivot on — detection must rely entirely on behavioural and graph signals stored in D1. The detection approach builds a lightweight interaction graph in D1, scores edge density between anonymous session clusters, and flags dense sub-graphs for review using a Cloudflare Worker triggered on a scheduled cron.

---

## 1. Interaction Graph Schema in D1

```sql
-- Nodes: anonymous session handles (ephemeral, no PII)
CREATE TABLE IF NOT EXISTS anon_sessions (
  session_hash TEXT PRIMARY KEY,   -- SHA-256 of ephemeral session token
  first_seen   INTEGER NOT NULL,
  last_seen    INTEGER NOT NULL,
  action_count INTEGER NOT NULL DEFAULT 0
);

-- Directed edges: session A co-acted with session B on the same content
CREATE TABLE IF NOT EXISTS interaction_edges (
  src_hash     TEXT NOT NULL,
  dst_hash     TEXT NOT NULL,
  content_id   TEXT NOT NULL,
  action_type  TEXT NOT NULL,  -- 'like' | 'reply' | 'boost'
  acted_at     INTEGER NOT NULL,
  PRIMARY KEY (src_hash, dst_hash, content_id, action_type)
);

CREATE INDEX idx_edges_dst   ON interaction_edges (dst_hash, acted_at);
CREATE INDEX idx_edges_src   ON interaction_edges (src_hash, acted_at);
CREATE INDEX idx_edges_content ON interaction_edges (content_id, acted_at);
```

---

## 2. Edge Insertion on Content Interaction

When a session acts on a piece of content, write an edge to every other session that acted on the same content within the last 5 minutes (co-action window).

```typescript
const CO_ACTION_WINDOW_MS = 5 * 60 * 1000;

export async function recordInteraction(
  sessionHash: string,
  contentId: string,
  actionType: string,
  env: Env,
): Promise<void> {
  const now = Date.now();
  const cutoff = now - CO_ACTION_WINDOW_MS;

  // Upsert the acting session
  await env.DB.prepare(
    `INSERT INTO anon_sessions (session_hash, first_seen, last_seen, action_count)
     VALUES (?, ?, ?, 1)
     ON CONFLICT(session_hash) DO UPDATE
     SET last_seen = excluded.last_seen,
         action_count = action_count + 1`,
  ).bind(sessionHash, now, now).run();

  // Find co-actors on the same content in the window
  const coActors = await env.DB.prepare(
    `SELECT DISTINCT src_hash FROM interaction_edges
     WHERE content_id = ? AND acted_at > ?`,
  ).bind(contentId, cutoff).all<{ src_hash: string }>();

  // Insert bidirectional edges in batch
  const stmts = coActors.results.flatMap(({ src_hash }) => [
    env.DB.prepare(
      `INSERT OR IGNORE INTO interaction_edges
       (src_hash, dst_hash, content_id, action_type, acted_at)
       VALUES (?, ?, ?, ?, ?)`,
    ).bind(sessionHash, src_hash, contentId, actionType, now),
    env.DB.prepare(
      `INSERT OR IGNORE INTO interaction_edges
       (src_hash, dst_hash, content_id, action_type, acted_at)
       VALUES (?, ?, ?, ?, ?)`,
    ).bind(src_hash, sessionHash, contentId, actionType, now),
  ]);

  if (stmts.length > 0) await env.DB.batch(stmts);
}
```

---

## 3. Edge Density Scoring (Scheduled Worker)

A cron Worker computes a density score for each pair of sessions: how many distinct content items they co-acted on within the last 24 hours.

```typescript
// wrangler.toml: [triggers] crons = ["0 * * * *"]
export async function detectDenseClusters(env: Env): Promise<void> {
  const windowMs = 24 * 60 * 60 * 1000;
  const cutoff = Date.now() - windowMs;
  const DENSITY_THRESHOLD = 5; // 5+ shared content items in 24 h = suspicious

  const densePairs = await env.DB.prepare(
    `SELECT src_hash, dst_hash, COUNT(DISTINCT content_id) AS shared_count
     FROM interaction_edges
     WHERE acted_at > ?
     GROUP BY src_hash, dst_hash
     HAVING shared_count >= ?`,
  ).bind(cutoff, DENSITY_THRESHOLD).all<{
    src_hash: string;
    dst_hash: string;
    shared_count: number;
  }>();

  if (densePairs.results.length === 0) return;

  const flagStmts = densePairs.results.map(({ src_hash, dst_hash, shared_count }) =>
    env.DB.prepare(
      `INSERT OR REPLACE INTO sock_puppet_flags
       (src_hash, dst_hash, shared_count, flagged_at)
       VALUES (?, ?, ?, ?)`,
    ).bind(src_hash, dst_hash, shared_count, Date.now()),
  );

  await env.DB.batch(flagStmts);
}
```

Schema for flags:

```sql
CREATE TABLE IF NOT EXISTS sock_puppet_flags (
  src_hash     TEXT NOT NULL,
  dst_hash     TEXT NOT NULL,
  shared_count INTEGER NOT NULL,
  flagged_at   INTEGER NOT NULL,
  reviewed     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (src_hash, dst_hash)
);
```

---

## 4. Cluster Expansion via Transitive Closure

Dense pairs alone miss multi-hop networks. Expand clusters by following edges from flagged nodes.

```typescript
async function expandCluster(
  seedHash: string,
  env: Env,
  depth = 2,
): Promise<Set<string>> {
  const visited = new Set<string>([seedHash]);
  const frontier = [seedHash];

  for (let d = 0; d < depth; d++) {
    if (frontier.length === 0) break;
    const placeholders = frontier.map(() => "?").join(",");
    const rows = await env.DB.prepare(
      `SELECT DISTINCT dst_hash FROM sock_puppet_flags
       WHERE src_hash IN (${placeholders}) AND reviewed = 0`,
    ).bind(...frontier).all<{ dst_hash: string }>();

    const next: string[] = [];
    for (const { dst_hash } of rows.results) {
      if (!visited.has(dst_hash)) {
        visited.add(dst_hash);
        next.push(dst_hash);
      }
    }
    frontier.length = 0;
    frontier.push(...next);
  }

  return visited;
}
```

---

## 5. Temporal Coordination Score

Sessions acting within a very tight time window (< 3 seconds apart) on the same content are more suspicious than those acting minutes apart.

```typescript
async function temporalCoordinationScore(
  sessionA: string,
  sessionB: string,
  contentId: string,
  env: Env,
): Promise<number> {
  const rows = await env.DB.prepare(
    `SELECT a.acted_at AS t_a, b.acted_at AS t_b
     FROM interaction_edges a
     JOIN interaction_edges b
       ON a.content_id = b.content_id
      AND a.src_hash = ?
      AND b.src_hash = ?
     WHERE a.content_id = ?`,
  ).bind(sessionA, sessionB, contentId).all<{ t_a: number; t_b: number }>();

  if (rows.results.length === 0) return 0;

  const tightCount = rows.results.filter(
    ({ t_a, t_b }) => Math.abs(t_a - t_b) < 3000,
  ).length;

  return tightCount / rows.results.length; // 0-1; higher = more coordinated
}
```

---

## Anti-patterns

- **Pivoting on IP address alone**: residential proxies and VPNs make IP-based graph edges meaningless; graph edges must be built from content co-action, not network proximity.
- **Flagging pairs without reviewing transitive clusters**: a ring of 10 accounts with moderate pairwise density is more dangerous than one dense pair; always expand the cluster before actioning.
- **Immediate account action on flag creation**: graph flags are probabilistic signals; route flagged clusters to a human review queue before restricting accounts.
- **Keeping interaction edges indefinitely**: unbounded edge growth will make D1 queries slow; prune edges older than 30 days with a nightly cron.
- **Using `SELECT *` on large edge tables in the cron job**: always project only necessary columns and apply the time-window filter to use the index.

## Gotchas

- D1 does not support recursive CTEs for transitive closure in a single SQL statement — use the iterative TypeScript expansion pattern above.
- `INSERT OR IGNORE` on the edge primary key prevents duplicate edges but does not update `acted_at`; use `INSERT OR REPLACE` if you want the most recent timestamp.
- `COUNT(DISTINCT content_id)` in the density query can be slow on large `interaction_edges` tables; ensure `(src_hash, dst_hash, content_id)` is indexed or partition the query by time window.
- Scheduled Workers in Cloudflare have a CPU time limit of 30 seconds (Bundled plan) or 15 minutes (Unbound); for large graphs break the cron job into paginated batches using a KV cursor.
- Session hash collisions across users are theoretically possible with SHA-256 truncation; use the full 64-hex-character hash to keep collision probability negligible.

## Verification

1. Insert synthetic edges simulating two sessions co-acting on 6 distinct content items within 24 h; confirm a `sock_puppet_flags` row appears after the cron runs.
2. Run `expandCluster` from one flagged seed; verify it returns all connected nodes in the test fixture's transitive closure.
3. Confirm `temporalCoordinationScore` returns > 0.8 for a pair whose actions are all within 1 second.
4. Delete edges older than 30 days via a test cleanup job and verify the density query returns 0 for that pair.
5. Check D1 query explain plan for the density query; confirm the `acted_at` index is used.

## Related

- `coordinated-inauthentic-behavior-detection-d1.md`
- `content-farm-spam-network-detection-d1.md`
- `platform-manipulation-brigading-detection.md`
- `repeat-offender-detection-anonymous-sessions.md`
- `ban-evasion-device-fingerprint-detection-d1.md`

## Sources

- Cloudflare D1 documentation — batched statements, indexes, cron Workers
- "Sock Puppet Detection on Social Platforms via Graph Analysis" — ACM WebSci 2024
- GIFCT Technical Working Group — coordinated network detection playbook 2025
- Cloudflare Workers scheduled events documentation
