# Coordinated Inauthentic Behavior Detection: Account Clustering with D1 Graph Queries

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Groups of accounts on example project exhibit suspicious synchrony: they register within minutes of each other, share identical posting cadences, amplify the same content within seconds, and use overlapping device fingerprints. Individual account-level signals miss the network; you need graph-based clustering to surface coordinated inauthentic behavior (CIB) before the campaign reaches critical mass.

---

## Context

CIB detection requires building a behavioral graph where nodes are accounts and edges represent shared signals (same IP subnet, same device fingerprint, same content hash, synchronous like bursts). Clusters within this graph are CIB candidates. On example project the entire pipeline runs inside Cloudflare Workers + D1, without external graph databases. SQLite's recursive CTE support makes adjacency-list traversal viable for moderate-sized graphs (< 500k nodes).

Meta's CIB enforcement framework and Stanford Internet Observatory research define CIB as three or more accounts acting in concert to artificially amplify content while concealing the coordination. The platform's obligation under DSA Article 34 is to assess and mitigate systemic risk from such campaigns.

---

## Section 1: Signal Collection Schema

```sql
-- migration 0031_cib_signals.sql

-- Shared behavioral signals between pairs of accounts
CREATE TABLE IF NOT EXISTS cib_signal (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  account_a   TEXT    NOT NULL,
  account_b   TEXT    NOT NULL,
  signal_type TEXT    NOT NULL,  -- IP_SUBNET | DEVICE_FP | CONTENT_HASH | LIKE_BURST | REG_WINDOW
  weight      REAL    NOT NULL DEFAULT 1.0,
  observed_at INTEGER NOT NULL,
  CHECK (account_a < account_b)  -- canonical order prevents duplicate edges
);

CREATE INDEX IF NOT EXISTS idx_cib_signal_a   ON cib_signal (account_a, signal_type);
CREATE INDEX IF NOT EXISTS idx_cib_signal_b   ON cib_signal (account_b, signal_type);
CREATE INDEX IF NOT EXISTS idx_cib_signal_ts  ON cib_signal (observed_at);

-- Derived clusters (written by the detection Worker)
CREATE TABLE IF NOT EXISTS cib_cluster (
  cluster_id    TEXT    NOT NULL,
  account_id    TEXT    NOT NULL,
  confidence    REAL    NOT NULL,
  first_seen_at INTEGER NOT NULL,
  PRIMARY KEY (cluster_id, account_id)
);
```

---

## Section 2: Signal Ingestion at Event Time

Signals are emitted from multiple Workers (auth, post, like, search) and written to D1 asynchronously via `waitUntil`.

```typescript
// src/cib/signal-writer.ts
import type { Env } from '../types';

export type SignalType = 'IP_SUBNET' | 'DEVICE_FP' | 'CONTENT_HASH' | 'LIKE_BURST' | 'REG_WINDOW';

export async function recordSharedSignal(
  env: Env,
  accountA: string,
  accountB: string,
  signalType: SignalType,
  weight = 1.0
): Promise<void> {
  // Enforce canonical ordering so (A,B) and (B,A) are the same edge.
  const [a, b] = [accountA, accountB].sort();

  await env.DB
    .prepare(
      `INSERT INTO cib_signal (account_a, account_b, signal_type, weight, observed_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT DO NOTHING`
    )
    .bind(a, b, signalType, weight, Date.now())
    .run();
}

// Called from the auth Worker when two accounts share a /24 subnet on registration
export async function onRegistration(env: Env, accountId: string, ip: string, ctx: ExecutionContext): Promise<void> {
  const subnet = ip.split('.').slice(0, 3).join('.');

  const { results } = await env.DB
    .prepare(
      `SELECT account_id FROM accounts
       WHERE ip_subnet = ? AND account_id != ?
         AND created_at > ?`
    )
    .bind(subnet, accountId, Date.now() - 3_600_000) // 1h window
    .all<{ account_id: string }>();

  ctx.waitUntil(
    Promise.all(
      results.map(r => recordSharedSignal(env, accountId, r.account_id, 'IP_SUBNET', 0.6))
    )
  );
}
```

---

## Section 3: Like-Burst Detection

When three or more accounts like the same post within a 30-second window, record pairwise LIKE_BURST signals.

```typescript
// src/cib/like-burst.ts
import { recordSharedSignal } from './signal-writer';
import type { Env } from '../types';

const BURST_WINDOW_MS = 30_000;
const BURST_WEIGHT    = 1.2; // higher weight — harder to fake accidentally

export async function onLike(
  env: Env,
  actorId: string,
  postId: string,
  ctx: ExecutionContext
): Promise<void> {
  const windowStart = Date.now() - BURST_WINDOW_MS;

  const { results } = await env.DB
    .prepare(
      `SELECT account_id FROM post_likes
       WHERE post_id = ? AND account_id != ? AND liked_at > ?`
    )
    .bind(postId, actorId, windowStart)
    .all<{ account_id: string }>();

  if (results.length >= 2) {
    ctx.waitUntil(
      Promise.all(
        results.map(r =>
          recordSharedSignal(env, actorId, r.account_id, 'LIKE_BURST', BURST_WEIGHT)
        )
      )
    );
  }
}
```

---

## Section 4: Graph Clustering with Recursive CTE

D1 (SQLite) supports `WITH RECURSIVE` for adjacency-list graph traversal. The query below performs connected-component labeling: starting from a seed account it expands to all reachable accounts via edges whose aggregate weight exceeds a threshold.

```typescript
// src/cib/cluster-query.ts
import type { Env } from '../types';

interface ClusterRow {
  account_id: string;
  total_weight: number;
  depth: number;
}

const MIN_EDGE_WEIGHT = 2.0;  // sum of weights for an edge to count
const MAX_DEPTH       = 5;    // prevent runaway traversal

export async function findCluster(
  env: Env,
  seedAccountId: string
): Promise<ClusterRow[]> {
  const { results } = await env.DB
    .prepare(
      `WITH RECURSIVE
       -- Aggregate weights per pair to filter weak edges
       edges(a, b, w) AS (
         SELECT account_a, account_b, SUM(weight)
         FROM cib_signal
         GROUP BY account_a, account_b
         HAVING SUM(weight) >= ?
       ),
       -- Undirected adjacency expansion
       cluster(account_id, total_weight, depth) AS (
         SELECT ?, 0.0, 0
         UNION
         SELECT
           CASE WHEN e.a = c.account_id THEN e.b ELSE e.a END,
           c.total_weight + e.w,
           c.depth + 1
         FROM cluster c
         JOIN edges e ON (e.a = c.account_id OR e.b = c.account_id)
         WHERE c.depth < ?
       )
       SELECT account_id, MAX(total_weight) AS total_weight, MAX(depth) AS depth
       FROM cluster
       GROUP BY account_id
       ORDER BY total_weight DESC`
    )
    .bind(MIN_EDGE_WEIGHT, seedAccountId, MAX_DEPTH)
    .all<ClusterRow>();

  return results;
}
```

---

## Section 5: Scheduled Cluster Materialization

Run the full clustering sweep hourly. For each account with recent signals, expand its cluster, assign a stable UUID, and persist to `cib_cluster`.

```typescript
// src/workers/cib-sweep.ts  — scheduled cron: "0 * * * *"
import { findCluster } from '../cib/cluster-query';
import type { Env } from '../types';
import { randomUUID } from 'crypto';

const MIN_CLUSTER_SIZE = 3; // DSA / Meta CIB threshold

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const windowStart = Date.now() - 86_400_000; // 24h

    const { results: seeds } = await env.DB
      .prepare(
        `SELECT DISTINCT account_a AS account_id FROM cib_signal WHERE observed_at > ?
         UNION
         SELECT DISTINCT account_b FROM cib_signal WHERE observed_at > ?`
      )
      .bind(windowStart, windowStart)
      .all<{ account_id: string }>();

    const seen = new Set<string>();

    for (const { account_id } of seeds) {
      if (seen.has(account_id)) continue;

      const members = await findCluster(env, account_id);
      if (members.length < MIN_CLUSTER_SIZE) continue;

      const clusterId = randomUUID();
      const now       = Date.now();

      const stmts = members.map(m =>
        env.DB.prepare(
          `INSERT INTO cib_cluster (cluster_id, account_id, confidence, first_seen_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT DO NOTHING`
        ).bind(clusterId, m.account_id, Math.min(m.total_weight / 10, 1.0), now)
      );

      await env.DB.batch(stmts);
      members.forEach(m => seen.add(m.account_id));

      console.log(`CIB cluster ${clusterId}: ${members.length} accounts`);
    }
  },
};
```

---

## Section 6: Enforcement Integration

Once a cluster reaches a confidence threshold, it can trigger automated enforcement (shadow ban, rate limit, human review queue).

```typescript
// src/cib/enforce.ts
import { applyShadowBan } from '../moderation/shadow-ban';
import type { Env } from '../types';

const HIGH_CONFIDENCE = 0.8;

export async function enforceCibCluster(env: Env, clusterId: string): Promise<void> {
  const { results } = await env.DB
    .prepare(
      `SELECT account_id, confidence FROM cib_cluster
       WHERE cluster_id = ? AND confidence >= ?`
    )
    .bind(clusterId, HIGH_CONFIDENCE)
    .all<{ account_id: string; confidence: number }>();

  for (const { account_id } of results) {
    await applyShadowBan(env, {
      accountId:   account_id,
      appliedBy:   'cib-sweep',
      reasonCode:  'CIB',
      visibility:  'degraded',
      ttlSeconds:  86_400 * 7, // 7-day hold pending human review
      auditJson:   { clusterId, detectedAt: Date.now() },
    });
  }
}
```

---

## Anti-patterns

- **Single-signal clustering** — one shared IP is insufficient; require multi-signal convergence before enforcement action.
- **Unbounded CTE depth** — without `WHERE c.depth < ?`, the recursive query can fan out across the entire graph, timing out in Workers (50 ms CPU budget).
- **Writing signals synchronously** — blocking the request path on D1 writes adds latency; always use `ctx.waitUntil`.
- **Materializing the full graph in-memory** — for graphs > 10k nodes, edge-list in D1 will overflow Workers memory (128 MB). Consider a dedicated R2 export for offline analysis at that scale.
- **Over-relying on IP signals** — CGNAT means thousands of legitimate users share a single IPv4 /24. Weight IP signals low and require corroborating behavioral signals.

---

## Gotchas

- SQLite `WITH RECURSIVE` can return duplicate rows in non-UNION forms; use `UNION` (not `UNION ALL`) to deduplicate during expansion.
- D1's 30-second statement timeout will kill cluster queries on very large signal tables. Index `cib_signal (account_a, account_b)` and keep the look-back window short.
- `CHECK (account_a < account_b)` in the signal table requires the application to sort before inserting — enforce this in `recordSharedSignal`, not at call sites.
- Cluster IDs are not stable across sweeps unless you key them by canonical seed. Use deterministic UUIDs (UUID v5 over sorted member list) if stable references matter for appeals.

---

## Verification

```bash
# Seed test signals for three accounts
for pair in "acct-001 acct-002" "acct-001 acct-003" "acct-002 acct-003"; do
  read a b <<< "$pair"
  wrangler d1 execute example project-db --command \
    "INSERT INTO cib_signal (account_a,account_b,signal_type,weight,observed_at)
     VALUES ('$a','$b','LIKE_BURST',1.5,$(date +%s)000)"
done

# Trigger manual sweep
wrangler workers tail --name cib-sweep

# Verify cluster materialized
wrangler d1 execute example project-db --command \
  "SELECT * FROM cib_cluster ORDER BY first_seen_at DESC LIMIT 10"
```

---

## Related

- `shadow-banning-reach-limiting-d1-workers.md`
- `platform-manipulation-brigading-detection.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `repeat-offender-detection-anonymous-sessions.md`
- `dsa-risk-assessment.md`

---

## Sources

- Meta Transparency Center: Coordinated Inauthentic Behavior — https://transparency.fb.com/policies/community-standards/coordinated-inauthentic-behavior/
- Stanford Internet Observatory CIB research — https://cyber.fsi.stanford.edu/io
- SQLite WITH RECURSIVE documentation — https://www.sqlite.org/lang_with.html
- DSA Article 34 (Systemic Risk Assessment) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
- Cloudflare D1 — https://developers.cloudflare.com/d1/
