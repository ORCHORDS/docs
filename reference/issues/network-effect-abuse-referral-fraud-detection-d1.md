# Network-Effect Abuse & Referral Fraud Detection (D1)

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project's invite-and-referral system grants referrers bonus reach, reputation points, or monetisation unlocks when a new anonymous user joins via their link. Abusers create chains of sock-puppet accounts (all from the same device cluster or IP range) to farm these rewards at scale. Classic velocity checks miss the fraud because each individual account looks legitimate in isolation; only the graph structure reveals the scheme.

---

## Context

Anonymous platforms cannot use email-graph deduplication. Instead, D1 stores lightweight referral edges keyed on hashed device fingerprints, Cloudflare Turnstile token IDs, and CF-IPCountry + ASN tuples. A scheduled Cron Trigger walks the edge table, computes depth and fan-out metrics, and flags sub-trees that exhibit referral-farm topology. No PII is stored; all identifiers are one-way hashed at ingestion time.

---

## 1. Schema — D1 Referral Graph Tables

```sql
-- migrations/0022_referral_graph.sql
CREATE TABLE IF NOT EXISTS referral_edges (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  referrer_hash  TEXT    NOT NULL,   -- SHA-256(session_token)
  referee_hash   TEXT    NOT NULL,
  device_hash    TEXT    NOT NULL,   -- SHA-256(fp_token)
  asn            INTEGER NOT NULL,
  country        TEXT    NOT NULL,
  created_at     INTEGER NOT NULL    -- Unix epoch seconds
);

CREATE INDEX idx_re_referrer ON referral_edges(referrer_hash, created_at);
CREATE INDEX idx_re_device   ON referral_edges(device_hash);

CREATE TABLE IF NOT EXISTS referral_fraud_flags (
  root_hash      TEXT    PRIMARY KEY,
  depth          INTEGER NOT NULL,
  fan_out        INTEGER NOT NULL,
  unique_devices INTEGER NOT NULL,
  unique_asns    INTEGER NOT NULL,
  score          REAL    NOT NULL,
  flagged_at     INTEGER NOT NULL,
  actioned       INTEGER NOT NULL DEFAULT 0   -- 0 = pending, 1 = actioned
);
```

---

## 2. Ingestion Worker — Recording a Referral Edge

```typescript
// src/workers/referral-ingest.ts
import { Env } from '../types';
import { sha256Hex } from '../lib/crypto';
import { getCfInfo } from '../lib/cf';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { referrerToken, refereeToken, fpToken } = await request.json<{
      referrerToken: string;
      refereeToken: string;
      fpToken: string;
    }>();

    if (!referrerToken || !refereeToken || !fpToken) {
      return new Response('Bad Request', { status: 400 });
    }

    const { asn, country } = getCfInfo(request);

    const [referrerHash, refereeHash, deviceHash] = await Promise.all([
      sha256Hex(referrerToken),
      sha256Hex(refereeToken),
      sha256Hex(fpToken),
    ]);

    // Reject self-referral
    if (referrerHash === refereeHash) {
      return new Response(JSON.stringify({ ok: false, reason: 'self_referral' }), { status: 422 });
    }

    await env.DB.prepare(
      `INSERT OR IGNORE INTO referral_edges
         (referrer_hash, referee_hash, device_hash, asn, country, created_at)
       VALUES (?, ?, ?, ?, ?, unixepoch())`
    )
      .bind(referrerHash, refereeHash, deviceHash, asn, country)
      .run();

    return new Response(JSON.stringify({ ok: true }), { status: 201 });
  },
};
```

---

## 3. Fraud-Scoring Cron — Graph Walk

```typescript
// src/cron/referral-fraud-scan.ts
import { Env } from '../types';

interface EdgeRow {
  referrer_hash: string;
  referee_hash: string;
  device_hash: string;
  asn: number;
}

export async function runReferralFraudScan(env: Env): Promise<void> {
  // Pull all edges created in the last 48 h
  const cutoff = Math.floor(Date.now() / 1000) - 172_800;
  const { results } = await env.DB.prepare(
    `SELECT referrer_hash, referee_hash, device_hash, asn
       FROM referral_edges
      WHERE created_at > ?`
  )
    .bind(cutoff)
    .all<EdgeRow>();

  // Build adjacency map: referrer → set of referees
  const adjacency = new Map<string, Set<string>>();
  const devicesByNode = new Map<string, Set<string>>();
  const asnsByNode = new Map<string, Set<number>>();

  for (const row of results) {
    if (!adjacency.has(row.referrer_hash)) adjacency.set(row.referrer_hash, new Set());
    adjacency.get(row.referrer_hash)!.add(row.referee_hash);

    for (const node of [row.referrer_hash, row.referee_hash]) {
      if (!devicesByNode.has(node)) devicesByNode.set(node, new Set());
      devicesByNode.get(node)!.add(row.device_hash);
      if (!asnsByNode.has(node)) asnsByNode.set(node, new Set());
      asnsByNode.get(node)!.add(row.asn);
    }
  }

  // Identify root nodes (nodes that appear only as referrers, never as referees)
  const allReferees = new Set(results.map(r => r.referee_hash));
  const roots = [...adjacency.keys()].filter(n => !allReferees.has(n));

  const stmtUpsert = env.DB.prepare(
    `INSERT INTO referral_fraud_flags
       (root_hash, depth, fan_out, unique_devices, unique_asns, score, flagged_at)
     VALUES (?, ?, ?, ?, ?, ?, unixepoch())
     ON CONFLICT(root_hash) DO UPDATE SET
       depth = excluded.depth,
       fan_out = excluded.fan_out,
       unique_devices = excluded.unique_devices,
       unique_asns = excluded.unique_asns,
       score = excluded.score,
       flagged_at = excluded.flagged_at`
  );

  for (const root of roots) {
    const { depth, totalNodes, deviceSet, asnSet } = bfsMetrics(root, adjacency, devicesByNode, asnsByNode);
    const fanOut = adjacency.get(root)?.size ?? 0;

    // Fraud score heuristic:
    // high depth + high fan-out + low unique devices/ASNs = farm
    const deviceDiversity = deviceSet.size / Math.max(totalNodes, 1);
    const asnDiversity = asnSet.size / Math.max(totalNodes, 1);
    const score = (depth * 0.3 + fanOut * 0.3) * (1 - deviceDiversity * 0.5) * (1 - asnDiversity * 0.2);

    if (score > 4.0) {
      await stmtUpsert
        .bind(root, depth, fanOut, deviceSet.size, asnSet.size, score)
        .run();
    }
  }
}

function bfsMetrics(
  root: string,
  adjacency: Map<string, Set<string>>,
  devicesByNode: Map<string, Set<string>>,
  asnsByNode: Map<string, Set<number>>
): { depth: number; totalNodes: number; deviceSet: Set<string>; asnSet: Set<number> } {
  const visited = new Set<string>();
  const queue: Array<{ node: string; depth: number }> = [{ node: root, depth: 0 }];
  let maxDepth = 0;
  const deviceSet = new Set<string>();
  const asnSet = new Set<number>();

  while (queue.length > 0) {
    const { node, depth } = queue.shift()!;
    if (visited.has(node)) continue;
    visited.add(node);
    maxDepth = Math.max(maxDepth, depth);
    for (const d of devicesByNode.get(node) ?? []) deviceSet.add(d);
    for (const a of asnsByNode.get(node) ?? []) asnSet.add(a);

    for (const child of adjacency.get(node) ?? []) {
      if (!visited.has(child)) queue.push({ node: child, depth: depth + 1 });
    }
  }

  return { depth: maxDepth, totalNodes: visited.size, deviceSet, asnSet };
}
```

---

## 4. Action Worker — Suppressing Flagged Trees

```typescript
// src/workers/referral-fraud-action.ts
import { Env } from '../types';

export async function suppressFraudulentReferralTree(
  rootHash: string,
  env: Env
): Promise<{ suppressed: number }> {
  // Walk descendants in D1 and strip pending reward grants
  const { results } = await env.DB.prepare(
    `WITH RECURSIVE tree(node) AS (
       SELECT referee_hash FROM referral_edges WHERE referrer_hash = ?
       UNION ALL
       SELECT re.referee_hash
         FROM referral_edges re
         JOIN tree t ON re.referrer_hash = t.node
     )
     SELECT node FROM tree`
  )
    .bind(rootHash)
    .all<{ node: string }>();

  if (results.length === 0) return { suppressed: 0 };

  const placeholders = results.map(() => '?').join(',');
  const hashes = results.map(r => r.node);

  await env.DB.prepare(
    `UPDATE reward_grants
        SET status = 'suppressed', suppressed_reason = 'referral_fraud'
      WHERE beneficiary_hash IN (${placeholders}) AND status = 'pending'`
  )
    .bind(...hashes)
    .run();

  await env.DB.prepare(
    `UPDATE referral_fraud_flags SET actioned = 1 WHERE root_hash = ?`
  )
    .bind(rootHash)
    .run();

  return { suppressed: results.length };
}
```

---

## 5. Wrangler Cron Configuration

```toml
# wrangler.toml (relevant excerpt)
[[d1_databases]]
binding     = "DB"
database_name = "example project-prod"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[triggers]
crons = ["0 */6 * * *"]   # run every 6 hours
```

---

## Anti-patterns

- **Trusting client-supplied referrer tokens without re-hashing server-side.** Always re-derive the hash in the Worker; never echo back raw tokens.
- **Running the BFS on every request.** The graph walk is O(V+E) over 48 h of data; run it only in the Cron Trigger, never in the hot path.
- **Flagging solely on depth.** A legitimate influencer can have deep trees. Score must combine depth, fan-out, device diversity, and ASN diversity.
- **Cascade-deleting accounts without human review.** Flag and suppress rewards first; escalate to trust-and-safety before account termination.

---

## Gotchas

- D1's recursive CTE support requires `WITH RECURSIVE`; plain `WITH` does not do recursion.
- `INSERT OR IGNORE` on `referral_edges` prevents duplicate edges from double-submissions but requires a UNIQUE constraint — add one if your schema does not have it.
- ASN 0 may appear for Cloudflare's own internal traffic; exclude it from diversity calculations.
- The BFS in the Cron Worker is in-memory and will OOM if the graph exceeds ~100 k nodes in a single 48 h window; chunk by `created_at` buckets if volume is that high.

---

## Verification

```typescript
// tests/referral-fraud.test.ts
import { describe, it, expect } from 'vitest';
import { bfsMetrics } from '../src/cron/referral-fraud-scan';

describe('bfsMetrics', () => {
  it('detects a three-level farm with one shared device', () => {
    const adjacency = new Map([
      ['root', new Set(['a', 'b', 'c'])],
      ['a',    new Set(['d', 'e'])],
      ['b',    new Set(['f'])],
    ]);
    const devicesByNode = new Map(
      ['root','a','b','c','d','e','f'].map(n => [n, new Set(['device1'])])
    );
    const asnsByNode = new Map(
      ['root','a','b','c','d','e','f'].map(n => [n, new Set([12345])])
    );
    const result = bfsMetrics('root', adjacency, devicesByNode, asnsByNode);
    expect(result.depth).toBe(2);
    expect(result.deviceSet.size).toBe(1);
  });
});
```

---

## Related

- `sock-puppet-network-detection.md`
- `anonymous-account-graph-clustering-d1.md`
- `sybil-attack-detection-workers-ai-behavioral.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `platform-token-economy-abuse-prevention.md`

---

## Sources

- Cloudflare D1 — Recursive CTEs: https://developers.cloudflare.com/d1/
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- "Sybil-Resistant Referral Systems", USENIX Security 2023
- GIFCT — Graph-based Coordinated Inauthentic Behaviour Signals
