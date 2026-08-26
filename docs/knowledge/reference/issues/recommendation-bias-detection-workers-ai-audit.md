# Recommendation Bias Detection & Audit — Workers AI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

example project's feed algorithm surfaces content based on engagement signals. Over time, implicit
feedback loops can cause the recommender to systematically under-surface content from certain
topics, languages, or community clusters — without any explicit policy decision to do so. The
EU DSA (Article 27) and emerging platform-equity obligations require platforms to audit their
recommendation systems for disparate impact and report findings. This article covers how to
detect, measure, and surface recommendation bias using Workers AI and D1.

---

## Context

Recommendation bias on anonymous platforms is particularly insidious because:
- There is no user demographic to correlate against, so standard fairness metrics
  (demographic parity, equalized odds) cannot be applied directly.
- Proxy attributes — content language, topic cluster, posting time, community shard — must
  substitute for demographic categories.
- The recommender's outputs (impression counts, click-through rate, dwell time) are observable
  even when the algorithm itself is a black box.

The audit pipeline has three stages:
1. **Sample collection** — draw stratified impression logs from D1 by content cluster.
2. **Bias scoring** — use Workers AI embeddings to cluster content and measure exposure gaps.
3. **Report generation** — emit structured findings to an audit log and optionally alert
   platform operators.

---

## Schema: Impression Log in D1

```sql
CREATE TABLE impressions (
  id           TEXT PRIMARY KEY,
  content_id   TEXT NOT NULL,
  cluster_tag  TEXT,             -- topic cluster assigned at ingest
  language     TEXT,
  shown_at     INTEGER NOT NULL, -- unix ms
  clicked      INTEGER DEFAULT 0,
  dwell_ms     INTEGER DEFAULT 0
);

CREATE INDEX idx_impressions_cluster ON impressions (cluster_tag, shown_at);
CREATE INDEX idx_impressions_lang    ON impressions (language, shown_at);
```

---

## 1. Stratified Sample Collection

Pull impression rates per cluster for a rolling window to detect exposure gaps.

```typescript
interface ClusterStats {
  cluster: string;
  impressions: number;
  clicks: number;
  avg_dwell: number;
}

async function collectClusterStats(
  db: D1Database,
  windowMs = 7 * 86_400_000
): Promise<ClusterStats[]> {
  const since = Date.now() - windowMs;
  const { results } = await db
    .prepare(
      `SELECT cluster_tag AS cluster,
              COUNT(*)           AS impressions,
              SUM(clicked)       AS clicks,
              AVG(dwell_ms)      AS avg_dwell
       FROM impressions
       WHERE shown_at > ? AND cluster_tag IS NOT NULL
       GROUP BY cluster_tag
       ORDER BY impressions DESC`
    )
    .bind(since)
    .all<ClusterStats>();
  return results;
}
```

---

## 2. Exposure Disparity Score

Compare each cluster's impression share to its content share (how many posts exist per
cluster). A significant gap indicates the recommender is over- or under-surfacing that cluster.

```typescript
async function computeExposureDisparity(
  db: D1Database,
  stats: ClusterStats[]
): Promise<Array<ClusterStats & { disparity: number }>> {
  const { results: contentCounts } = await db
    .prepare(
      `SELECT cluster_tag AS cluster, COUNT(*) AS cnt
       FROM posts WHERE cluster_tag IS NOT NULL GROUP BY cluster_tag`
    )
    .all<{ cluster: string; cnt: number }>();

  const contentShare = new Map(contentCounts.map((r) => [r.cluster, r.cnt]));
  const totalContent = [...contentShare.values()].reduce((a, b) => a + b, 0);
  const totalImpressions = stats.reduce((a, s) => a + s.impressions, 0);

  return stats.map((s) => {
    const expectedShare = (contentShare.get(s.cluster) ?? 0) / totalContent;
    const actualShare = s.impressions / totalImpressions;
    // Positive = over-exposed, negative = under-exposed
    const disparity = actualShare - expectedShare;
    return { ...s, disparity };
  });
}
```

---

## 3. Semantic Cluster Auditing with Workers AI

For clusters defined by topic rather than explicit tags, use Workers AI embeddings to detect
whether semantically similar content receives similar exposure.

```typescript
async function embedClusterLabel(
  ai: Ai,
  label: string
): Promise<number[]> {
  const response = await ai.run("@cf/baai/bge-base-en-v1.5", {
    text: [label],
  });
  return response.data[0];
}

function cosineSimilarity(a: number[], b: number[]): number {
  const dot = a.reduce((s, v, i) => s + v * b[i], 0);
  const normA = Math.sqrt(a.reduce((s, v) => s + v * v, 0));
  const normB = Math.sqrt(b.reduce((s, v) => s + v * v, 0));
  return dot / (normA * normB);
}

async function findSemanticallySimilarUnderexposedClusters(
  ai: Ai,
  scored: Array<{ cluster: string; disparity: number }>
): Promise<Array<{ pairA: string; pairB: string; similarity: number; disparityGap: number }>> {
  const embeddings = await Promise.all(
    scored.map(async (s) => ({ ...s, vec: await embedClusterLabel(ai, s.cluster) }))
  );

  const findings: Array<{ pairA: string; pairB: string; similarity: number; disparityGap: number }> = [];
  for (let i = 0; i < embeddings.length; i++) {
    for (let j = i + 1; j < embeddings.length; j++) {
      const sim = cosineSimilarity(embeddings[i].vec, embeddings[j].vec);
      const gap = Math.abs(embeddings[i].disparity - embeddings[j].disparity);
      // Semantically similar topics with big exposure gap = likely bias
      if (sim > 0.85 && gap > 0.05) {
        findings.push({
          pairA: embeddings[i].cluster,
          pairB: embeddings[j].cluster,
          similarity: sim,
          disparityGap: gap,
        });
      }
    }
  }
  return findings;
}
```

---

## 4. Audit Log Emission

Write structured findings to a D1 audit table and optionally push to an Analytics Engine
dataset for dashboarding.

```typescript
async function writeAuditFindings(
  db: D1Database,
  findings: Array<{ pairA: string; pairB: string; similarity: number; disparityGap: number }>
): Promise<void> {
  const stmt = db.prepare(
    `INSERT INTO recommendation_audit (id, pair_a, pair_b, similarity, disparity_gap, audited_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  );
  const batch = findings.map((f) =>
    stmt.bind(crypto.randomUUID(), f.pairA, f.pairB, f.similarity, f.disparityGap, Date.now())
  );
  await db.batch(batch);
}
```

---

## 5. Scheduled Audit Worker

```typescript
// wrangler.toml: [triggers] crons = ["0 3 * * *"]
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const stats = await collectClusterStats(env.DB);
    const scored = await computeExposureDisparity(env.DB, stats);
    const biasedPairs = await findSemanticallySimilarUnderexposedClusters(env.AI, scored);
    if (biasedPairs.length > 0) {
      await writeAuditFindings(env.DB, biasedPairs);
      // Alert operator via internal webhook
      await fetch(env.ALERT_WEBHOOK, {
        method: "POST",
        body: JSON.stringify({ event: "bias_detected", count: biasedPairs.length }),
        headers: { "Content-Type": "application/json" },
      });
    }
  },
};
```

---

## Anti-patterns

- **Auditing only CTR** — dwell time and re-engagement are better quality signals; CTR can
  be gamed by clickbait regardless of cluster.
- **Treating content volume as ground truth** — high-volume clusters can legitimately warrant
  higher exposure; use engagement-adjusted expected share where data permits.
- **Running the audit synchronously in the request path** — embedding calls are slow; always
  run as a scheduled job.
- **Storing raw post text in the audit log** — store cluster IDs only; raw content in audit
  logs creates unnecessary data-retention risk.

---

## Gotchas

- Workers AI `@cf/baai/bge-base-en-v1.5` returns 768-dimensional vectors. The pairwise
  comparison loop is O(n²) — cap cluster count at ~200 before switching to approximate
  nearest-neighbour approaches.
- D1 `AVG(dwell_ms)` silently ignores NULLs; ensure dwell is always written as 0 on
  non-click impressions rather than left NULL.
- The `disparity > 0.05` threshold is empirical — tune against your content mix. Sparse
  clusters (< 100 posts) should be excluded from the analysis to avoid noise.
- DSA Article 27 requires that audit methodology be documented and available to regulators.
  Keep the audit schema and scoring logic versioned.

---

## Verification

```bash
# Seed two semantically similar clusters with mismatched exposure
wrangler d1 execute example project_DB --command "
  INSERT INTO impressions VALUES ('i1','c1','politics-environment','en',1700000000000,1,5000);
  INSERT INTO impressions VALUES ('i2','c1','politics-environment','en',1700000001000,0,0);
  INSERT INTO impressions VALUES ('i3','c2','politics-climate','en',1700000002000,0,0);
"
# Run scheduled handler locally
wrangler dev --test-scheduled
# Check audit table
wrangler d1 execute example project_DB --command "SELECT * FROM recommendation_audit"
```

---

## Related

- `platform-health-score-dashboard-analytics-engine.md`
- `election-misinformation-detection-workers-ai.md`
- `eu-dsa-recommender-2026.md`
- `real-time-toxic-content-scoring-workers-ai.md`

---

## Sources

- EU DSA Article 27 — recommender system transparency obligations
- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- "Auditing Recommender Systems for Bias" — ACM FAccT 2024
- example project internal feed algorithm spec v3.0
