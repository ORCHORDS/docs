# Astroturfing Detection via Network Analysis — Workers AI + D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Organised campaigns create large numbers of anonymous example project sessions that all upvote, share, and comment on the same set of posts within a short time window, manufacturing the appearance of organic grassroots support for a topic or brand while hiding the coordination. Unlike coordinated inauthentic behaviour at the account level, astroturfing targets *content amplification* — the goal is not to pollute discussion but to shift perceived consensus.

## Context

example project surfaces trending content using an engagement score derived from reactions and shares. Because sessions are anonymous, astroturfing rings cannot be detected by account-graph analysis; instead example project detects structural patterns: temporal clustering of upvotes, low textual diversity in comments, shared Cloudflare Ray-ID prefixes (suggesting same datacenter origin), and suspiciously uniform time-to-first-action (TTF) distributions. D1 stores per-content engagement vectors; Workers AI computes embedding similarity over comment batches.

## Detection — Temporal Cluster and Embedding Similarity

```typescript
// workers/astroturf-detector.ts
import { Ai } from "@cloudflare/ai";

interface Env {
  AI: Ai;
  DB: D1Database;
  ANALYTICS: AnalyticsEngineDataset;
  THROTTLE_KV: KVNamespace;
  FLAG_QUEUE: Queue;
}

interface EngagementEvent {
  contentId: string;
  sessionId: string;
  actionType: "upvote" | "share" | "comment";
  commentText?: string;
  rayId: string;       // Cloudflare-Request-ID prefix (first 8 chars)
  ts: number;          // unix ms
}

const CLUSTER_WINDOW_MS = 5 * 60 * 1000;   // 5-minute burst window
const MIN_CLUSTER_SIZE  = 10;               // ≥10 sessions needed to flag
const SIM_THRESHOLD     = 0.92;             // cosine similarity for near-duplicate comments

async function embedTexts(texts: string[], env: Env): Promise<number[][]> {
  const ai = new Ai(env.AI);
  const result = await ai.run("@cf/baai/bge-small-en-v1.5", { text: texts });
  return (result as { data: number[][] }).data;
}

function cosineSim(a: number[], b: number[]): number {
  const dot = a.reduce((s, v, i) => s + v * (b[i] ?? 0), 0);
  const normA = Math.sqrt(a.reduce((s, v) => s + v * v, 0));
  const normB = Math.sqrt(b.reduce((s, v) => s + v * v, 0));
  return normA && normB ? dot / (normA * normB) : 0;
}

async function detectTemporalCluster(
  contentId: string,
  windowStartMs: number,
  env: Env
): Promise<{ clusterSize: number; uniqueRayPrefixes: number }> {
  const windowStart = new Date(windowStartMs).toISOString();
  const result = await env.DB.prepare(
    `SELECT
       COUNT(DISTINCT session_id) AS cluster_size,
       COUNT(DISTINCT ray_prefix)  AS unique_ray_prefixes
     FROM content_engagements
     WHERE content_id  = ?
       AND occurred_at >= ?
       AND occurred_at <= datetime(?, '+5 minutes')`
  )
    .bind(contentId, windowStart, windowStart)
    .first<{ cluster_size: number; unique_ray_prefixes: number }>();

  return {
    clusterSize: result?.cluster_size ?? 0,
    uniqueRayPrefixes: result?.unique_ray_prefixes ?? 0,
  };
}

async function detectCommentSimilarity(
  contentId: string,
  sinceMs: number,
  env: Env
): Promise<number> {
  const since = new Date(sinceMs - CLUSTER_WINDOW_MS).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT comment_text FROM content_engagements
     WHERE content_id = ? AND comment_text IS NOT NULL AND occurred_at >= ?
     ORDER BY occurred_at DESC LIMIT 40`
  )
    .bind(contentId, since)
    .all<{ comment_text: string }>();

  if (results.length < 4) return 0;

  const texts = results.map((r) => r.comment_text);
  const vectors = await embedTexts(texts, env);

  let highSimPairs = 0;
  let totalPairs = 0;
  for (let i = 0; i < vectors.length; i++) {
    for (let j = i + 1; j < vectors.length; j++) {
      totalPairs++;
      if (cosineSim(vectors[i]!, vectors[j]!) >= SIM_THRESHOLD) highSimPairs++;
    }
  }
  return totalPairs > 0 ? highSimPairs / totalPairs : 0;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const event = await request.json<EngagementEvent>();

    // Write engagement to D1
    await env.DB.prepare(
      `INSERT INTO content_engagements
         (content_id, session_id, action_type, comment_text, ray_prefix, occurred_at)
       VALUES (?, ?, ?, ?, ?, datetime(?, 'unixepoch'))`
    )
      .bind(
        event.contentId,
        event.sessionId,
        event.actionType,
        event.commentText ?? null,
        event.rayId.slice(0, 8),
        Math.floor(event.ts / 1000)
      )
      .run();

    // Write to Analytics Engine for real-time dashboard
    env.ANALYTICS.writeDataPoint({
      blobs: [event.contentId, event.actionType, event.rayId.slice(0, 8)],
      doubles: [event.ts],
      indexes: [event.contentId],
    });

    // Throttle: only score once per content per 60 s
    const throttleKey = `astro:${event.contentId}`;
    const alreadyScored = await env.THROTTLE_KV.get(throttleKey);
    if (alreadyScored) return new Response(JSON.stringify({ action: "allow" }), { status: 200 });
    await env.THROTTLE_KV.put(throttleKey, "1", { expirationTtl: 60 });

    const [cluster, simRatio] = await Promise.all([
      detectTemporalCluster(event.contentId, event.ts, env),
      event.actionType === "comment"
        ? detectCommentSimilarity(event.contentId, event.ts, env)
        : Promise.resolve(0),
    ]);

    // Ray-prefix diversity: low diversity = same infra origin
    const rayDiversityScore =
      cluster.clusterSize > 0
        ? 1 - cluster.uniqueRayPrefixes / cluster.clusterSize
        : 0;

    let riskScore = 0;
    if (cluster.clusterSize >= MIN_CLUSTER_SIZE) riskScore += 0.3;
    if (cluster.clusterSize >= MIN_CLUSTER_SIZE * 3) riskScore += 0.2;
    riskScore += rayDiversityScore * 0.25;
    riskScore += simRatio * 0.25;

    if (riskScore >= 0.6) {
      await env.FLAG_QUEUE.send({
        type: riskScore >= 0.8 ? "ASTRO_HIGH" : "ASTRO_REVIEW",
        contentId: event.contentId,
        riskScore,
        clusterSize: cluster.clusterSize,
        uniqueRayPrefixes: cluster.uniqueRayPrefixes,
        simRatio,
        ts: Date.now(),
      });
    }

    return new Response(JSON.stringify({ riskScore }), { status: 200 });
  },
};
```

## Response and Enforcement — Score Suppression

```typescript
// workers/astroturf-responder.ts
interface AstroEvent {
  type: "ASTRO_HIGH" | "ASTRO_REVIEW";
  contentId: string;
  riskScore: number;
  clusterSize: number;
  uniqueRayPrefixes: number;
  simRatio: number;
  ts: number;
}

export default {
  async queue(batch: MessageBatch<AstroEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const evt = msg.body;

      // Record detection
      await env.DB.prepare(
        `INSERT OR REPLACE INTO astroturf_flags
           (content_id, risk_score, cluster_size, unique_ray_prefixes,
            sim_ratio, flag_type, flagged_at)
         VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
      )
        .bind(
          evt.contentId, evt.riskScore, evt.clusterSize,
          evt.uniqueRayPrefixes, evt.simRatio, evt.type
        )
        .run();

      if (evt.type === "ASTRO_HIGH") {
        // Suppress content from trending algorithm by zeroing its boost score
        await env.DB.prepare(
          `UPDATE content_items
             SET trending_boost = 0, astroturf_suppressed = 1,
                 suppressed_at = CURRENT_TIMESTAMP
           WHERE content_id = ?`
        ).bind(evt.contentId).run();

        // Attach a "disputed organic reach" label visible to moderators
        await env.DB.prepare(
          `INSERT OR IGNORE INTO content_labels
             (content_id, label, applied_by, applied_at)
           VALUES (?, 'astroturf_suppressed', 'system', CURRENT_TIMESTAMP)`
        ).bind(evt.contentId).run();
      }

      msg.ack();
    }
  },
};
```

## Audit and Compliance — Schema and Weekly Report

```sql
-- D1 migration
CREATE TABLE IF NOT EXISTS content_engagements (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id   TEXT NOT NULL,
  session_id   TEXT NOT NULL,
  action_type  TEXT NOT NULL,
  comment_text TEXT,
  ray_prefix   TEXT NOT NULL,
  occurred_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eng_content_time
  ON content_engagements(content_id, occurred_at);

CREATE TABLE IF NOT EXISTS astroturf_flags (
  content_id          TEXT PRIMARY KEY,
  risk_score          REAL NOT NULL,
  cluster_size        INTEGER NOT NULL,
  unique_ray_prefixes INTEGER NOT NULL,
  sim_ratio           REAL NOT NULL,
  flag_type           TEXT NOT NULL,
  flagged_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content_labels (
  content_id TEXT NOT NULL,
  label      TEXT NOT NULL,
  applied_by TEXT NOT NULL,
  applied_at TEXT NOT NULL,
  PRIMARY KEY (content_id, label)
);

-- Weekly astroturfing report
SELECT
  strftime('%Y-%W', flagged_at) AS week,
  COUNT(*)                       AS flagged_content,
  SUM(flag_type = 'ASTRO_HIGH')  AS high_confidence,
  AVG(risk_score)                AS avg_risk,
  AVG(cluster_size)              AS avg_cluster
FROM astroturf_flags
GROUP BY week
ORDER BY week DESC
LIMIT 8;
```

## Anti-patterns

- **Using account-level graph analysis** — example project has no persistent accounts; session-graph edges are meaningless after the session expires.
- **Suppressing content based on cluster size alone** — a genuine breaking-news post will attract rapid organic engagement; always require at least two independent signals.
- **Exposing suppression status to the poster** — confirms detection; use silent suppression (reach limiting) instead.
- **Embedding every comment in real time** — embedding is expensive; batch-compute on a throttle gate or sample 1-in-5 comments below cluster threshold.
- **Treating Ray-ID prefix as a reliable origin fingerprint** — Cloudflare's anycast means the same prefix can serve diverse users; use it as a weak corroborating signal, not primary evidence.

## Gotchas

- `@cf/baai/bge-small-en-v1.5` accepts a maximum of 512 tokens per text input — truncate long comments before embedding.
- The Workers AI batch endpoint accepts up to 100 texts per call; chunk if you have more.
- Analytics Engine `writeDataPoint` is fire-and-forget and does not block the response; do not await it.
- D1's `datetime()` modifier syntax (`datetime(ts, 'unixepoch')`) requires the epoch value to be in **seconds**, not milliseconds.
- `ON CONFLICT ... DO UPDATE` on `astroturf_flags` replaces an older lower-confidence record — intentional, but ensure the content-label insert uses `OR IGNORE` to avoid losing manual labels.

## Verification

```bash
# 1. Simulate a 15-session burst on content "post-xyz" within 2 minutes
for i in $(seq 1 15); do
  curl -s -X POST https://example.com/internal/engagement-event \
    -H "Content-Type: application/json" \
    -d "{\"contentId\":\"post-xyz\",\"sessionId\":\"s$i\",
         \"actionType\":\"upvote\",\"rayId\":\"abc12345\",\"ts\":$(date +%s%3N)}" &
done; wait

# 2. Check astroturf_flags
wrangler d1 execute example project-db --command \
  "SELECT risk_score, cluster_size, flag_type FROM astroturf_flags WHERE content_id='post-xyz';"

# 3. Verify trending_boost zeroed
wrangler d1 execute example project-db --command \
  "SELECT trending_boost, astroturf_suppressed FROM content_items WHERE content_id='post-xyz';"

# 4. Check content_labels
wrangler d1 execute example project-db --command \
  "SELECT * FROM content_labels WHERE content_id='post-xyz';"
```

## Related

- `coordinated-inauthentic-behavior-detection-d1.md`
- `platform-manipulation-brigading-detection.md`
- `real-time-toxic-content-scoring-workers-ai.md`
- `recommendation-bias-detection-workers-ai-audit.md`
- `spam-post-detection-cloudflare-workers-ai.md`

## Sources

- https://transparency.fb.com/policies/community-standards/coordinated-inauthentic-behavior/
- https://help.twitter.com/en/rules-and-policies/platform-manipulation
- https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/
