# Anonymous Account Graph Clustering for Suspicious Activity Detection (D1)

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

On example project (example.com), accounts are anonymous by design — no email, no phone, no real identity. Adversaries exploit this to create clusters of throwaway accounts that coordinate to amplify content, harass targets, or game ranking algorithms. The problem is not any single account acting badly, but the invisible graph of accounts that share behavioral, timing, or device signals pointing to the same origin.

Detecting such clusters requires building and querying a relationship graph entirely from behavioral telemetry without touching PII. D1's relational model, combined with periodic Workers jobs and a lightweight community-detection algorithm running in-Worker, provides an effective pipeline for this.

## Context

example project accounts are identified only by an anonymous session token derived from Cloudflare Turnstile attestation and a per-install random ID. Despite this, coordinated actors leave fingerprints: they post within seconds of each other, use the same shared IP subnet or ASN, react to the same niche posts in lockstep, or were all created within the same five-minute window.

The detection system stores edge observations in D1 (Cloudflare's SQLite-at-edge), runs a union-find clustering routine inside a scheduled Worker, and writes cluster risk scores back to D1 where downstream moderation Workers can query them. No raw device data is stored — only hashed co-occurrence signals that cannot be reverse-engineered into identifying information.

## Graph Edge Collection

Each time two accounts share a signal (same post interaction burst, same IP /24, same device canvas-hash bucket), a Worker inserts or upserts an edge record. Edges are stored with a weight that decays over time so old co-occurrences naturally fade.

```typescript
// worker: edge-collector.ts
export interface Env {
  DB: D1Database;
}

interface SignalEvent {
  accountA: string; // hashed anon token
  accountB: string;
  signalType: 'ip_subnet' | 'timing_burst' | 'interaction_sync' | 'device_bucket';
  strength: number; // 0-1, caller-supplied
}

export async function recordEdge(env: Env, event: SignalEvent): Promise<void> {
  // Canonical ordering so (A,B) and (B,A) are the same row
  const [nodeA, nodeB] = [event.accountA, event.accountB].sort();

  await env.DB.prepare(`
    INSERT INTO account_edges (node_a, node_b, signal_type, weight, last_seen)
    VALUES (?1, ?2, ?3, ?4, unixepoch())
    ON CONFLICT(node_a, node_b, signal_type) DO UPDATE SET
      weight    = MIN(1.0, excluded.weight + account_edges.weight * 0.8),
      last_seen = unixepoch()
  `).bind(nodeA, nodeB, event.signalType, event.strength).run();
}

// Schema (run via migration):
// CREATE TABLE account_edges (
//   node_a      TEXT NOT NULL,
//   node_b      TEXT NOT NULL,
//   signal_type TEXT NOT NULL,
//   weight      REAL NOT NULL DEFAULT 0,
//   last_seen   INTEGER NOT NULL,
//   PRIMARY KEY (node_a, node_b, signal_type)
// );
// CREATE INDEX idx_edges_node_a ON account_edges(node_a);
// CREATE INDEX idx_edges_node_b ON account_edges(node_b);
```

## Cluster Detection via Union-Find

A scheduled Worker loads the current high-weight edge set from D1 and runs an in-memory union-find (disjoint set union) to materialise clusters. This runs at most every 15 minutes; the cluster table is the output consumed by moderation downstream.

```typescript
// worker: cluster-builder.ts  (scheduled trigger)
export interface Env {
  DB: D1Database;
}

class UnionFind {
  private parent: Map<string, string> = new Map();
  private rank: Map<string, number> = new Map();

  find(x: string): string {
    if (!this.parent.has(x)) {
      this.parent.set(x, x);
      this.rank.set(x, 0);
    }
    if (this.parent.get(x) !== x) {
      this.parent.set(x, this.find(this.parent.get(x)!));
    }
    return this.parent.get(x)!;
  }

  union(a: string, b: string): void {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra === rb) return;
    const rankA = this.rank.get(ra) ?? 0;
    const rankB = this.rank.get(rb) ?? 0;
    if (rankA < rankB) {
      this.parent.set(ra, rb);
    } else if (rankA > rankB) {
      this.parent.set(rb, ra);
    } else {
      this.parent.set(rb, ra);
      this.rank.set(ra, rankA + 1);
    }
  }

  clusters(): Map<string, string[]> {
    const out: Map<string, string[]> = new Map();
    for (const node of this.parent.keys()) {
      const root = this.find(node);
      const arr = out.get(root) ?? [];
      arr.push(node);
      out.set(root, arr);
    }
    return out;
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Pull edges with combined weight above threshold, seen in last 48 h
    const edges = await env.DB.prepare(`
      SELECT node_a, node_b, SUM(weight) AS total_weight
      FROM account_edges
      WHERE last_seen > unixepoch() - 172800
      GROUP BY node_a, node_b
      HAVING total_weight >= 0.6
    `).all<{ node_a: string; node_b: string; total_weight: number }>();

    const uf = new UnionFind();
    for (const edge of edges.results) {
      uf.union(edge.node_a, edge.node_b);
    }

    const clusters = uf.clusters();
    const statements: D1PreparedStatement[] = [];

    for (const [root, members] of clusters) {
      if (members.length < 3) continue; // single pair is noise

      const clusterId = root;
      const size = members.length;
      // Risk scales with cluster size; very large clusters are near-certain abuse
      const riskScore = Math.min(1.0, 0.3 + (size - 3) * 0.07);

      statements.push(
        env.DB.prepare(`
          INSERT INTO account_clusters (cluster_id, member_count, risk_score, updated_at)
          VALUES (?1, ?2, ?3, unixepoch())
          ON CONFLICT(cluster_id) DO UPDATE SET
            member_count = excluded.member_count,
            risk_score   = excluded.risk_score,
            updated_at   = unixepoch()
        `).bind(clusterId, size, riskScore)
      );

      for (const member of members) {
        statements.push(
          env.DB.prepare(`
            INSERT INTO account_cluster_members (account_id, cluster_id, updated_at)
            VALUES (?1, ?2, unixepoch())
            ON CONFLICT(account_id) DO UPDATE SET
              cluster_id = excluded.cluster_id,
              updated_at = unixepoch()
          `).bind(member, clusterId)
        );
      }
    }

    // D1 batch limit: 1000 statements per call
    for (let i = 0; i < statements.length; i += 900) {
      await env.DB.batch(statements.slice(i, i + 900));
    }
  },
};
```

## Cluster Risk Query in Moderation Workers

Any Worker handling a content action can look up whether the acting account belongs to a high-risk cluster and apply additional scrutiny.

```typescript
// worker: moderation-gate.ts
export interface Env {
  DB: D1Database;
}

interface AccountRisk {
  clusterId: string | null;
  clusterSize: number;
  riskScore: number;
}

export async function getAccountClusterRisk(
  env: Env,
  accountId: string
): Promise<AccountRisk> {
  const row = await env.DB.prepare(`
    SELECT
      acm.cluster_id,
      ac.member_count,
      ac.risk_score
    FROM account_cluster_members acm
    JOIN account_clusters ac ON ac.cluster_id = acm.cluster_id
    WHERE acm.account_id = ?1
  `).bind(accountId).first<{
    cluster_id: string;
    member_count: number;
    risk_score: number;
  }>();

  if (!row) {
    return { clusterId: null, clusterSize: 1, riskScore: 0 };
  }

  return {
    clusterId: row.cluster_id,
    clusterSize: row.member_count,
    riskScore: row.risk_score,
  };
}

// Usage in a content submission handler:
export async function handlePost(
  request: Request,
  env: Env,
  accountId: string
): Promise<Response> {
  const risk = await getAccountClusterRisk(env, accountId);

  if (risk.riskScore >= 0.85) {
    return new Response('Account action temporarily restricted', { status: 403 });
  }

  if (risk.riskScore >= 0.6) {
    // Queue for human review instead of publishing immediately
    await queueForReview(env, accountId, request);
    return new Response('Submitted for review', { status: 202 });
  }

  return await publishContent(request, env, accountId);
}

async function queueForReview(_env: Env, _accountId: string, _req: Request): Promise<void> {
  // stub — see report-queue-prioritization article
}
async function publishContent(_req: Request, _env: Env, _accountId: string): Promise<Response> {
  return new Response('ok');
}
```

## Edge Decay and Graph Pruning

Without decay, the graph grows unbounded. A nightly scheduled Worker removes edges older than 7 days and updates weights using an exponential decay formula so stale co-occurrences lose influence gradually.

```typescript
// worker: graph-pruner.ts (scheduled, nightly)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Hard-delete edges not seen in 7 days
    await env.DB.prepare(`
      DELETE FROM account_edges WHERE last_seen < unixepoch() - 604800
    `).run();

    // Decay weights of edges seen 24-48h ago by 20%
    await env.DB.prepare(`
      UPDATE account_edges
      SET weight = weight * 0.8
      WHERE last_seen BETWEEN unixepoch() - 172800 AND unixepoch() - 86400
        AND weight * 0.8 > 0.05
    `).run();

    // Remove edges whose weight has decayed below the noise floor
    await env.DB.prepare(`
      DELETE FROM account_edges WHERE weight < 0.05
    `).run();
  },
};
```

## Anti-patterns

- Storing raw IPs or device identifiers in the edge table — hash everything before storage; raw PII undermines the platform's privacy promise
- Running union-find on the full edge set in one pass — on example project scale this can exceed the 128 MB Worker memory limit; partition by connected component seed or use a cursor-based chunk approach
- Triggering clustering on every request — this is a batch operation; run it on a schedule and cache the results in the cluster tables
- Using cluster membership alone as a ban signal — cluster risk is a signal, not a verdict; route high-risk cluster members to human review or elevated scrutiny, not automatic hard-ban
- Forgetting to prune orphan rows in `account_cluster_members` after an account is deleted — foreign-key-style cleanup must be manual in D1

## Gotchas

- D1 `batch()` is limited to 1000 statements; for large cluster updates, loop in chunks of 900 with buffer
- `unixepoch()` in SQLite returns seconds, not milliseconds — edge collection from JavaScript `Date.now()` must divide by 1000 before binding
- Union-find path compression mutates the `parent` map during iteration; do not iterate `parent` and call `find()` simultaneously — build the cluster map in a second pass
- A cluster of size 2 is often a false positive (two friends on the same home IP); use a minimum cluster size of 3-5 before acting
- D1's SQLite does not support `RECURSIVE` CTEs in the edge case where you try to do graph traversal in SQL — keep graph logic in Worker JavaScript

## Verification

1. Seed D1 with synthetic edges forming two known clusters of size 5 and one isolated pair using the edge insertion function.
2. Run the cluster-builder Worker manually via `wrangler dev --test-scheduled`.
3. Query `account_clusters` — expect exactly one cluster row (the pair should be filtered by `member_count >= 3`).
4. Query `account_cluster_members` — confirm all 5 members map to the correct `cluster_id`.
5. Call `getAccountClusterRisk` for a member of the size-5 cluster and verify `riskScore >= 0.6`.
6. Advance `last_seen` values by 8 days in a test fixture and run the pruner; confirm edge rows are deleted and clusters are rebuilt with empty membership.

## Related

- `coordinated-inauthentic-behavior-detection-d1.md`
- `sock-puppet-network-detection.md`
- `ban-evasion-device-fingerprint-detection-d1.md`
- `platform-manipulation-brigading-detection.md`

## Sources

- Cloudflare D1 documentation — batch operations and SQLite dialect: https://developers.cloudflare.com/d1/
- CORDON / community detection survey (Fortunato 2010) for union-find baseline: https://arxiv.org/abs/0906.0612
- Cloudflare Workers scheduled triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
