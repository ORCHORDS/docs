# Sybil Attack Detection With Workers AI Behavioral Analysis

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Sybil attack occurs when a single actor creates many pseudonymous identities on example project to amplify votes, flood reporting queues with false positives, or manufacture artificial consensus. On an anonymous platform there are no email addresses or phone numbers to deduplicate on, so traditional identity-linking approaches fail. The platform needs behavioral and timing signals that reveal coordinated identity clusters without requiring persistent personal identifiers.

## Context

example project sessions are ephemeral but behavioral patterns — typing cadence, interaction timing, vocabulary fingerprints, and navigation sequences — are surprisingly stable across re-registrations. Workers AI runs inference at the edge with zero cold-start overhead, enabling real-time scoring of incoming sessions against a learned behavioral centroid stored per cluster in D1. Clusters that grow unusually fast or vote/report in lock-step trigger escalation workflows.

## Detection — Behavioral Feature Extraction at the Edge

On each session action (post, vote, report), a Worker extracts lightweight behavioral features and scores them against known Sybil cluster centroids using Workers AI text embeddings. The embedding distance between the incoming session and existing cluster centroids determines cluster assignment.

```typescript
// workers/sybil-detector.ts
export interface Env {
  AI: Ai;
  DB: D1Database;
}

interface BehavioralFeatures {
  sessionAgeMs: number;
  actionsPerMinute: number;
  vocabularySize: number;
  postLengthMean: number;
  reportTargetVariety: number; // unique targets / total reports
  interactionIntervalStdDevMs: number;
}

function featuresToText(f: BehavioralFeatures): string {
  return [
    `age:${Math.round(f.sessionAgeMs / 60000)}min`,
    `apm:${f.actionsPerMinute.toFixed(1)}`,
    `vocab:${f.vocabularySize}`,
    `postlen:${Math.round(f.postLengthMean)}`,
    `rpt_variety:${f.reportTargetVariety.toFixed(2)}`,
    `interval_dev:${Math.round(f.interactionIntervalStdDevMs)}ms`,
  ].join(" ");
}

async function embedFeatures(ai: Ai, features: BehavioralFeatures): Promise<number[]> {
  const text = featuresToText(features);
  const result = await ai.run("@cf/baai/bge-small-en-v1.5", { text: [text] });
  return (result as { data: number[][] }).data[0];
}

function cosineSimilarity(a: number[], b: number[]): number {
  const dot = a.reduce((sum, v, i) => sum + v * b[i], 0);
  const magA = Math.sqrt(a.reduce((s, v) => s + v * v, 0));
  const magB = Math.sqrt(b.reduce((s, v) => s + v * v, 0));
  return dot / (magA * magB);
}

export async function scoreSybilRisk(
  env: Env,
  sessionId: string,
  features: BehavioralFeatures
): Promise<{ riskScore: number; clusterId: string | null }> {
  const embedding = await embedFeatures(env.AI, features);

  const { results: centroids } = await env.DB.prepare(
    `SELECT cluster_id, centroid_json FROM sybil_clusters
     WHERE active = 1 ORDER BY member_count DESC LIMIT 50`
  ).all<{ cluster_id: string; centroid_json: string }>();

  let maxSimilarity = 0;
  let assignedCluster: string | null = null;

  for (const row of centroids) {
    const centroid: number[] = JSON.parse(row.centroid_json);
    const sim = cosineSimilarity(embedding, centroid);
    if (sim > maxSimilarity) {
      maxSimilarity = sim;
      assignedCluster = row.cluster_id;
    }
  }

  // Similarity > 0.92 to an existing cluster is suspicious
  const riskScore = maxSimilarity > 0.92 ? maxSimilarity : 0;

  await env.DB.prepare(
    `INSERT INTO session_sybil_scores (session_id, cluster_id, risk_score, scored_at)
     VALUES (?, ?, ?, datetime('now'))
     ON CONFLICT(session_id) DO UPDATE SET
       cluster_id = excluded.cluster_id,
       risk_score = excluded.risk_score,
       scored_at = excluded.scored_at`
  ).bind(sessionId, assignedCluster, riskScore).run();

  return { riskScore, clusterId: assignedCluster };
}
```

## Enforcement — Cluster Growth Rate Monitoring

A scheduled Worker checks cluster growth rates every 5 minutes. Clusters that gain more than 10 members in a single window are flagged as active Sybil networks, and all member sessions are soft-limited.

```typescript
// workers/sybil-cluster-enforcer.ts (scheduled)
export interface Env {
  DB: D1Database;
  MODERATION_QUEUE: Queue;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const windowStart = new Date(Date.now() - 5 * 60_000).toISOString();

    const { results: fastGrowingClusters } = await env.DB.prepare(
      `SELECT cluster_id, COUNT(*) as new_members
       FROM session_sybil_scores
       WHERE scored_at > ? AND risk_score > 0.92
       GROUP BY cluster_id
       HAVING new_members > 10`
    ).bind(windowStart).all<{ cluster_id: string; new_members: number }>();

    for (const cluster of fastGrowingClusters) {
      // Mark cluster as active Sybil network
      await env.DB.prepare(
        `UPDATE sybil_clusters SET flagged = 1, flagged_at = datetime('now')
         WHERE cluster_id = ?`
      ).bind(cluster.cluster_id).run();

      // Soft-limit all sessions in this cluster
      await env.DB.prepare(
        `INSERT INTO session_restrictions (session_id, restriction, expires_at)
         SELECT session_id, 'sybil-soft-limit', datetime('now', '+6 hours')
         FROM session_sybil_scores
         WHERE cluster_id = ? AND risk_score > 0.92
         ON CONFLICT(session_id) DO UPDATE SET
           restriction = 'sybil-soft-limit',
           expires_at = datetime('now', '+6 hours')`
      ).bind(cluster.cluster_id).run();

      // Enqueue for human review
      await env.MODERATION_QUEUE.send({
        type: "sybil-cluster-detected",
        clusterId: cluster.cluster_id,
        newMembers: cluster.new_members,
        detectedAt: new Date().toISOString(),
      });
    }
  },
};
```

## Escalation — Centroid Update and Hard Ban

When a moderator confirms a cluster as Sybil, all sessions are hard-banned and the centroid is archived as a reference fingerprint for future detection.

```typescript
// workers/sybil-confirm-handler.ts
export async function confirmSybilCluster(
  db: D1Database,
  clusterId: string,
  moderatorId: string
): Promise<{ bannedCount: number }> {
  // Hard-ban all sessions
  const { meta } = await db.prepare(
    `INSERT INTO banned_sessions (session_id, reason, banned_at, banned_by)
     SELECT s.session_id, 'sybil-network', datetime('now'), ?
     FROM session_sybil_scores s
     WHERE s.cluster_id = ? AND s.risk_score > 0.92
     ON CONFLICT(session_id) DO UPDATE SET reason = 'sybil-network'`
  ).bind(moderatorId, clusterId).run();

  // Archive the centroid as a reference signature
  await db.prepare(
    `UPDATE sybil_clusters
     SET active = 0, confirmed_sybil = 1, reviewed_by = ?, reviewed_at = datetime('now')
     WHERE cluster_id = ?`
  ).bind(moderatorId, clusterId).run();

  return { bannedCount: meta.changes };
}
```

## Monitoring — Risk Score Histogram

```typescript
// Query for on-call dashboard
const RISK_HISTOGRAM_QUERY = `
  SELECT
    ROUND(risk_score, 1) AS score_bucket,
    COUNT(*) AS sessions
  FROM session_sybil_scores
  WHERE scored_at > datetime('now', '-1 hour')
  GROUP BY score_bucket
  ORDER BY score_bucket DESC
`;

// Alert threshold: if >5% of scored sessions have risk_score > 0.92 within 15 min
const ALERT_QUERY = `
  SELECT
    COUNT(CASE WHEN risk_score > 0.92 THEN 1 END) * 100.0 / COUNT(*) AS pct_high_risk
  FROM session_sybil_scores
  WHERE scored_at > datetime('now', '-15 minutes')
`;
```

## Anti-patterns

- Using IP address as the sole Sybil signal — Tor/VPN users share addresses but aren't Sybil actors
- Storing raw embeddings in D1 TEXT columns without compression — a 384-dimension float array is ~3 KB per row
- Running centroid comparison synchronously in the request path for all 50 clusters — batch or cache top-N
- Hard-banning on the first cluster match without growth rate confirmation — false-positive risk is high
- Rebuilding centroids from scratch on every update — use incremental averaging: `new_centroid = (n*old + new) / (n+1)`

## Gotchas

- Workers AI embedding models have request-size limits; keep `featuresToText` output under 512 tokens
- D1 does not support native vector types; store centroid as JSON and compare in Worker memory
- `meta.changes` in D1 batch operations counts affected rows, not inserted rows — verify with a SELECT if you need exact new inserts
- Cosine similarity requires normalized vectors; `bge-small-en-v1.5` outputs L2-normalized vectors by default, but verify on model updates
- Scheduled Workers must be declared in `wrangler.toml` under `[triggers]` — they will silently not run otherwise

## Verification

1. Seed D1 with 3 known Sybil cluster centroids from the test fixture.
2. Submit 15 sessions with features matching centroid #1 within 5 minutes — expect cluster `flagged = 1` after the scheduled enforcer fires.
3. Confirm `session_restrictions` rows exist for all 15 sessions.
4. Call `confirmSybilCluster` and verify `banned_sessions` count matches.
5. Submit a new session with distinct features — confirm `risk_score < 0.5` and no restriction.

## Related

- `/documentation/docs/policies/issues/coordinated-inauthentic-behavior-detection-d1.md`
- `/documentation/docs/policies/issues/sock-puppet-network-detection.md`
- `/documentation/docs/policies/issues/synthetic-identity-fraud-detection-workers-ai.md`
- `/documentation/docs/policies/issues/botnet-registration-detection-turnstile-fingerprinting.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/queues/
- https://arxiv.org/abs/1002.1318 (SybilGuard — behavioral Sybil detection)
