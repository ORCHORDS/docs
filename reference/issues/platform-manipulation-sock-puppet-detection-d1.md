# Sock Puppet Network Detection with D1 and Workers AI

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A platform begins to notice coordinated inauthentic behavior: clusters of accounts that post similar content, vote together, and were registered within minutes of each other from overlapping IP ranges. Traditional per-account abuse signals miss the network because each individual account looks borderline-clean on its own.

## Context

Sock puppet detection requires correlating signals across accounts rather than within a single account. Cloudflare D1 holds the raw registration and behavioral data. Workers AI (Vectorize) stores content embeddings so that semantic similarity can be computed cheaply at query time. A cron-triggered Worker runs nightly clustering and writes results to a `suspicious_clusters` table. A separate admin Worker exposes a review queue and an approve/ban action endpoint.

Key signals:
- Shared IPv4 /24 subnet at registration time
- Identical or near-identical device fingerprint (User-Agent + canvas hash)
- Registration timestamps within a 10-minute sliding window
- Cosine similarity > 0.92 on post embeddings (Vectorize)

## D1 Schema and Clustering Worker

```typescript
// schema.sql (run once via wrangler d1 execute)
// CREATE TABLE IF NOT EXISTS accounts (
//   id TEXT PRIMARY KEY,
//   ip_subnet TEXT,           -- first 3 octets: '203.0.113'
//   device_fp TEXT,
//   registered_at INTEGER,    -- unix epoch seconds
//   vectorize_id TEXT
// );
//
// CREATE TABLE IF NOT EXISTS suspicious_clusters (
//   cluster_id   TEXT PRIMARY KEY,
//   accounts     TEXT,         -- JSON array of account IDs
//   evidence_json TEXT,        -- signal breakdown
//   flagged_at   INTEGER,
//   status       TEXT DEFAULT 'pending' -- pending | approved | dismissed
// );

import { Ai } from '@cloudflare/ai';

export interface Env {
  DB: D1Database;
  VECTORIZE: VectorizeIndex;
  AI: Ai;
}

// cron handler — scheduled nightly at 02:00 UTC
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    await runSockPuppetClustering(env);
  },
};

async function runSockPuppetClustering(env: Env): Promise<void> {
  // Step 1: Find candidate account pairs sharing IP subnet or device fingerprint
  const candidates = await env.DB.prepare(`
    SELECT a.id AS id_a, b.id AS id_b,
           a.ip_subnet, a.device_fp,
           a.registered_at AS reg_a, b.registered_at AS reg_b
    FROM   accounts a
    JOIN   accounts b ON (
             a.ip_subnet = b.ip_subnet OR a.device_fp = b.device_fp
           )
           AND a.id < b.id
           AND ABS(a.registered_at - b.registered_at) < 600  -- 10-min window
    WHERE  a.registered_at > unixepoch('now', '-7 days')
    LIMIT  5000
  `).all<{ id_a: string; id_b: string; ip_subnet: string;
            device_fp: string; reg_a: number; reg_b: number }>();

  if (!candidates.results.length) return;

  // Step 2: For each pair, fetch content similarity via Vectorize
  const clusters = new Map<string, Set<string>>();

  for (const row of candidates.results) {
    const [vecA, vecB] = await Promise.all([
      env.VECTORIZE.getByIds([row.id_a]),
      env.VECTORIZE.getByIds([row.id_b]),
    ]);
    if (!vecA[0] || !vecB[0]) continue;

    const sim = cosineSimilarity(
      vecA[0].values as number[],
      vecB[0].values as number[],
    );
    if (sim < 0.92) continue;

    // Union-find: merge into same cluster
    const keyA = findCluster(clusters, row.id_a);
    const keyB = findCluster(clusters, row.id_b);
    if (keyA !== keyB) {
      const merged = new Set([...clusters.get(keyA)!, ...clusters.get(keyB)!]);
      clusters.set(keyA, merged);
      clusters.delete(keyB);
    }
  }

  // Step 3: Write clusters with >= 3 members to D1
  const now = Math.floor(Date.now() / 1000);
  const stmt = env.DB.prepare(`
    INSERT OR REPLACE INTO suspicious_clusters
      (cluster_id, accounts, evidence_json, flagged_at, status)
    VALUES (?, ?, ?, ?, 'pending')
  `);

  const batch: D1PreparedStatement[] = [];
  for (const [clusterId, members] of clusters) {
    if (members.size < 3) continue;
    const evidence = { signal: 'subnet+fp+timestamp+content_sim', member_count: members.size };
    batch.push(stmt.bind(
      clusterId,
      JSON.stringify([...members]),
      JSON.stringify(evidence),
      now,
    ));
  }
  if (batch.length) await env.DB.batch(batch);
}

// --- helpers ---
function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i]; normA += a[i] ** 2; normB += b[i] ** 2;
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB) + 1e-9);
}

function findCluster(map: Map<string, Set<string>>, id: string): string {
  for (const [key, set] of map) if (set.has(id)) return key;
  map.set(id, new Set([id]));
  return id;
}
```

## Admin Review Queue

A separate `admin-worker` (behind Cloudflare Access) exposes:

- `GET /queue` — returns `status = 'pending'` clusters, paginated.
- `POST /action` — body `{ cluster_id, action: 'approve' | 'dismiss' }`. On `approve`, the Worker issues a batch `UPDATE accounts SET suspended = 1` for every member ID.

```typescript
export async function handleAction(req: Request, env: Env): Promise<Response> {
  const { cluster_id, action } = await req.json<{ cluster_id: string; action: string }>();
  if (!['approve', 'dismiss'].includes(action)) {
    return new Response('invalid action', { status: 400 });
  }

  const row = await env.DB.prepare(
    'SELECT accounts FROM suspicious_clusters WHERE cluster_id = ?',
  ).bind(cluster_id).first<{ accounts: string }>();

  if (!row) return new Response('not found', { status: 404 });

  const ids: string[] = JSON.parse(row.accounts);

  if (action === 'approve') {
    const suspendStmt = env.DB.prepare('UPDATE accounts SET suspended = 1 WHERE id = ?');
    await env.DB.batch(ids.map(id => suspendStmt.bind(id)));
  }

  await env.DB.prepare(
    "UPDATE suspicious_clusters SET status = ? WHERE cluster_id = ?",
  ).bind(action === 'approve' ? 'approved' : 'dismissed', cluster_id).run();

  return Response.json({ ok: true, affected: ids.length });
}
```

## Anti-patterns

- **Running clustering in a Fetch handler** — clustering a week of data can take minutes; always use a Cron Trigger with `ctx.waitUntil`.
- **Storing raw IP addresses in the cluster evidence** — hash or subnet-only representations limit PII exposure.
- **Auto-banning without human review** — false-positive clusters (e.g., shared university Wi-Fi) require a human approve step.
- **Querying Vectorize per-user inside the pair loop** — batch `getByIds` where possible to reduce round-trips.

## Gotchas

- D1's `LIMIT 5000` is a safety valve; add an index on `(ip_subnet, registered_at)` and `(device_fp, registered_at)` to keep the self-join efficient.
- Vectorize `getByIds` is limited to 100 IDs per call; paginate when a cluster is large.
- Content embeddings must be regenerated if the Vectorize index dimension changes — migration requires re-embedding all posts.
- The union-find here is in-memory; for very large candidate sets, implement it with a temporary D1 table.

## Verification

```bash
# Confirm clusters were written
wrangler d1 execute example project-db --command \
  "SELECT cluster_id, json_array_length(accounts) AS size, status FROM suspicious_clusters ORDER BY flagged_at DESC LIMIT 10;"

# Tail cron logs
wrangler tail sock-puppet-clustering-worker --format pretty
```

## Related

- `fake-review-detection-workers-ai-d1.md`
- `mental-health-crisis-escalation-pipeline-workers-ai.md`
- Cloudflare Vectorize docs — cosine similarity queries

## Sources

- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- Cloudflare Vectorize: https://developers.cloudflare.com/vectorize/
- Stanford Internet Observatory — coordinated inauthentic behavior research
