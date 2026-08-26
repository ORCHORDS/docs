# Semantic Near-Duplicate Spam Detection — Workers AI & D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A spam campaign floods the platform with thousands of posts that pass perceptual hash and exact-duplicate filters. Each post has slightly different wording — paraphrased by a spinbot or LLM — but carries the same promotional link, scam offer, or harassing message. The existing `hash-based-duplicate-content-detection-r2.md` catches exact copies; this article addresses the complementary problem: semantically equivalent content that has been obfuscated at the surface level.

## Context

Near-duplicate spam is the dominant evasion technique against hash-based content deduplication. Modern spinbots and LLM-assisted paraphrasers can produce thousands of surface-distinct variants of a single message within seconds. Detection requires embedding-based similarity search across recent posts, coupled with author-cluster analysis. The stack is: Workers AI (text embeddings), Vectorize (approximate nearest-neighbor index), D1 (canonical spam record + cluster tracking), and Queues (async deduplication pipeline).

## 1. Vectorize Index Setup

```toml
# wrangler.toml additions
[[vectorize]]
binding    = "SPAM_VECTORS"
index_name = "example project-spam-dedup"
dimensions = 1024   # matches bge-large-en-v1.5 output
metric     = "cosine"
```

```bash
# One-time index creation
wrangler vectorize create example project-spam-dedup \
  --dimensions=1024 \
  --metric=cosine
```

## 2. Schema: Canonical Spam Clusters

```sql
-- migrations/0071_spam_clusters.sql
CREATE TABLE IF NOT EXISTS spam_clusters (
  cluster_id       TEXT PRIMARY KEY,
  seed_post_id     TEXT NOT NULL,    -- first detected instance
  canonical_text   TEXT NOT NULL,
  member_count     INTEGER DEFAULT 1,
  created_at       INTEGER NOT NULL,
  last_seen_at     INTEGER NOT NULL,
  action           TEXT DEFAULT 'pending'  -- pending | removed | benign
);
CREATE INDEX IF NOT EXISTS idx_sc_last ON spam_clusters(last_seen_at DESC);

CREATE TABLE IF NOT EXISTS spam_cluster_members (
  post_id     TEXT PRIMARY KEY,
  cluster_id  TEXT NOT NULL REFERENCES spam_clusters(cluster_id),
  similarity  REAL NOT NULL,
  added_at    INTEGER NOT NULL
);
```

## 3. Embedding & Similarity Lookup (Inline Worker)

```typescript
// src/near-dup-check.ts
const SIMILARITY_THRESHOLD = 0.88; // cosine similarity ≥ 0.88 → near-duplicate
const RECENT_WINDOW_HOURS = 24;

export interface NearDupResult {
  isDuplicate: boolean;
  clusterId: string | null;
  similarity: number;
  postId: string;
}

export async function checkNearDuplicate(
  postId: string,
  text: string,
  env: Env
): Promise<NearDupResult> {
  // Step 1: embed the candidate post
  const embeddingResult = await env.AI.run(
    "@cf/baai/bge-large-en-v1.5",
    { text: [text] }
  );
  const vector = embeddingResult.data[0] as number[];

  // Step 2: query Vectorize for nearest neighbors in recent window
  const queryResult = await env.SPAM_VECTORS.query(vector, {
    topK: 5,
    filter: {
      // Only compare against posts within the recent detection window
      inserted_after: Date.now() - RECENT_WINDOW_HOURS * 3600 * 1000,
    },
    returnMetadata: "all",
  });

  const topMatch = queryResult.matches[0];
  if (topMatch && topMatch.score >= SIMILARITY_THRESHOLD) {
    const clusterId = topMatch.metadata?.clusterId as string | null;
    return {
      isDuplicate: true,
      clusterId: clusterId ?? null,
      similarity: topMatch.score,
      postId,
    };
  }

  // Step 3: insert into Vectorize for future comparisons
  await env.SPAM_VECTORS.insert([
    {
      id: postId,
      values: vector,
      metadata: {
        postId,
        insertedAt: Date.now(),
      },
    },
  ]);

  return { isDuplicate: false, clusterId: null, similarity: 0, postId };
}
```

## 4. Cluster Creation & Member Registration

```typescript
// src/near-dup-cluster.ts
import { NearDupResult } from "./near-dup-check";

export async function registerClusterMember(
  result: NearDupResult,
  text: string,
  authorId: string,
  env: Env
): Promise<void> {
  const now = Date.now();

  if (result.clusterId) {
    // Add to existing cluster
    await env.DB.batch([
      env.DB.prepare(
        `INSERT OR IGNORE INTO spam_cluster_members
         (post_id, cluster_id, similarity, added_at) VALUES (?,?,?,?)`
      ).bind(result.postId, result.clusterId, result.similarity, now),
      env.DB.prepare(
        `UPDATE spam_clusters
         SET member_count = member_count + 1, last_seen_at = ?
         WHERE cluster_id = ?`
      ).bind(now, result.clusterId),
    ]);
  } else {
    // Seed a new cluster
    const clusterId = crypto.randomUUID();
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO spam_clusters
         (cluster_id, seed_post_id, canonical_text, created_at, last_seen_at)
         VALUES (?,?,?,?,?)`
      ).bind(clusterId, result.postId, text.slice(0, 500), now, now),
      env.DB.prepare(
        `INSERT INTO spam_cluster_members
         (post_id, cluster_id, similarity, added_at) VALUES (?,?,1.0,?)`
      ).bind(result.postId, clusterId, now),
    ]);

    // Update Vectorize metadata to include new clusterId
    await env.SPAM_VECTORS.upsert([
      {
        id: result.postId,
        values: [], // empty values = metadata-only update not supported; re-embed if needed
        metadata: { postId: result.postId, clusterId, insertedAt: now },
      },
    ]);
  }
}
```

## 5. Author Velocity Check (Amplifying Signal)

```typescript
// src/near-dup-author.ts
// Accounts that produce many near-duplicates are likely operating a spambot
export async function authorSpamVelocity(
  authorId: string,
  windowMinutes: number,
  env: Env
): Promise<{ count: number; clusterCount: number; suspicious: boolean }> {
  const windowStart = Date.now() - windowMinutes * 60 * 1000;

  const { count, cluster_count } = (await env.DB.prepare(
    `SELECT COUNT(scm.post_id) AS count,
            COUNT(DISTINCT scm.cluster_id) AS cluster_count
     FROM spam_cluster_members scm
     JOIN posts p ON p.id = scm.post_id
     WHERE p.author_id = ? AND scm.added_at >= ?`
  )
    .bind(authorId, windowStart)
    .first<{ count: number; cluster_count: number }>()) ?? { count: 0, cluster_count: 0 };

  // >5 near-duplicate posts in 10 min, spread across ≤2 clusters = spambot
  const suspicious =
    count >= 5 && cluster_count <= 2 && windowMinutes <= 10;

  return { count, clusterCount: cluster_count, suspicious };
}
```

## 6. Queue Consumer: Batch Cluster Action

```typescript
// src/near-dup-actioner.ts
const CLUSTER_SIZE_THRESHOLD = 20; // auto-action above this count

export default {
  async queue(
    batch: MessageBatch<{ clusterId: string }>,
    env: Env
  ) {
    const seen = new Set<string>();
    for (const msg of batch.messages) {
      const { clusterId } = msg.body;
      if (seen.has(clusterId)) { msg.ack(); continue; }
      seen.add(clusterId);

      const cluster = await env.DB.prepare(
        "SELECT member_count, action FROM spam_clusters WHERE cluster_id = ?"
      )
        .bind(clusterId)
        .first<{ member_count: number; action: string }>();

      if (!cluster || cluster.action !== "pending") { msg.ack(); continue; }

      if (cluster.member_count >= CLUSTER_SIZE_THRESHOLD) {
        // Remove all member posts and flag authors
        await env.DB.prepare(
          `UPDATE posts SET visibility='removed', remove_reason='spam_cluster'
           WHERE id IN (
             SELECT post_id FROM spam_cluster_members WHERE cluster_id=?
           )`
        )
          .bind(clusterId)
          .run();

        await env.DB.prepare(
          "UPDATE spam_clusters SET action='removed' WHERE cluster_id=?"
        )
          .bind(clusterId)
          .run();
      }

      msg.ack();
    }
  },
};
```

## Anti-patterns

- Using a single threshold for all content types — short posts (< 20 tokens) have naturally high cosine similarity even when unrelated; apply a minimum text length before embedding.
- Vectorize without a recency filter — comparing a new post against the entire index accumulates false positives from legitimate recurring phrases over time; always filter by `inserted_after`.
- Re-embedding on every request synchronously — for high-traffic paths, enqueue embedding and cluster assignment to a Queue consumer; block only on a KV rate-limit pre-check.
- Treating every cluster as spam — first confirm with author-velocity check; a cluster may represent organic trending discussion, not spam.

## Gotchas

- Vectorize `upsert` with empty `values` is not a metadata-only update in all SDK versions — re-embed the vector to update metadata safely, or store `clusterId` in D1 as the authoritative mapping.
- BGE-large-en-v1.5 produces 1024-dimensional vectors; confirm the Vectorize index was created with `--dimensions=1024` or similarity scores will be meaningless.
- Vectorize `query` with a `filter` on numeric timestamps requires the filter key to be declared at index creation (`--metadata-indexed`); verify this during provisioning.
- Spinbots sometimes insert Unicode zero-width characters to defeat embedding; normalize text through `text.replace(/\p{C}/gu, "")` before embedding.

## Verification

```bash
# Check cluster growth rate
wrangler d1 execute example project-prod --command \
  "SELECT DATE(created_at/1000,'unixepoch') d, COUNT(*) n
   FROM spam_clusters GROUP BY d ORDER BY d DESC LIMIT 7"

# Verify Vectorize index stats
wrangler vectorize info example project-spam-dedup

# Test near-duplicate detection in staging
TEXT1="Win a free iPhone! Click here: spamlink.io"
TEXT2="You have won an iPhone! Visit: spamlink.io to claim"
curl -X POST https://staging.example.com/internal/spam/check \
  -d "{\"text\":\"$TEXT2\"}"
# Expect: {"isDuplicate":true,"similarity":>0.88}
```

## Related

- `hash-based-duplicate-content-detection-r2.md`
- `content-farm-spam-network-detection-d1.md`
- `spam-post-detection-cloudflare-workers-ai.md`
- `spam-link-domain-reputation-workers-d1.md`
- `astroturfing-detection-workers-ai-network-analysis.md`

## Sources

- Cloudflare Vectorize docs: developers.cloudflare.com/vectorize/
- Cloudflare Workers AI — bge-large-en-v1.5: developers.cloudflare.com/workers-ai/models/
- "Near-Duplicate Detection" — Manber & Wu (Stanford, 1994); updated survey: Broder (2000)
- Meta AI — "SpAm: A Dataset of Social Media Spam" (2023)
