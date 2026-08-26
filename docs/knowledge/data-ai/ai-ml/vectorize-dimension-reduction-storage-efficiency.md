# Vectorize Dimension Reduction for Storage Efficiency

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project indexes every public post into Vectorize for semantic search and
personalised feed ranking. The embedding model of choice is
`@cf/baai/bge-large-en-v1.5`, which produces 1 024-dimensional float32 vectors.
At 1 M posts × 1 024 dims × 4 bytes = ~4 GB of raw embedding storage, the
Vectorize index approaches the plan's vector-storage budget and query latency
creeps up as the index grows.

Goal: reduce stored dimensionality to 256–512 dims without rebuilding the embedding
model, preserving 95%+ of semantic retrieval quality, and cutting storage by 50–75%.

---

## Context

Three main strategies exist for reducing embedding dimensions after the fact:

1. **Truncation (Matryoshka models only)** — models trained with Matryoshka
   Representation Learning (MRL) encode meaningful information in every prefix of
   the vector. You can simply slice the first N dimensions and re-normalise.
   `bge-large-en-v1.5` supports MRL truncation to 512, 256, or 128 dims.

2. **PCA projection** — fit a Principal Component Analysis transform on a sample of
   your corpus, project all vectors into a lower-dimensional space. Works on any
   model but requires storing and applying the projection matrix at query time.

3. **Scalar quantisation (int8 / binary)** — convert each float32 component to an
   int8 or single bit. Cloudflare Vectorize natively supports `int8` and
   `float32`; binary is not yet supported. Int8 at original dimensionality cuts
   storage by 4× and can be combined with dimension truncation.

For example project, MRL truncation to 512 dims is the primary strategy because it
requires no projection matrix and the quality degradation is predictable and small.
Int8 quantisation is applied on top for an additional 4× storage saving, yielding
an 8× total reduction (1 024 f32 → 512 int8).

---

## Create a Reduced-Dimension Vectorize Index

```typescript
// scripts/create-reduced-index.ts
// Run with: wrangler d1 execute ... or via REST API

const VECTORIZE_API = "https://api.cloudflare.com/client/v4/accounts";

async function createReducedIndex(
  accountId: string,
  apiToken: string,
  indexName: string
) {
  const res = await fetch(
    `${VECTORIZE_API}/${accountId}/vectorize/v2/indexes`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: indexName,
        config: {
          dimensions: 512,        // MRL-truncated from 1 024
          metric: "cosine",       // re-normalise after truncation
        },
      }),
    }
  );

  const json = await res.json();
  console.log("Created index:", json);
}
```

---

## Generating Truncated Embeddings at Ingest Time

The `bge-large-en-v1.5` embedding is 1 024 floats. Slice the first 512 and
re-normalise to unit length before upserting into Vectorize.

```typescript
// src/lib/embedding.ts
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
}

/** Truncate and L2-normalise a float32 embedding. */
export function truncateAndNormalise(
  embedding: number[],
  targetDims: number
): number[] {
  const sliced = embedding.slice(0, targetDims);
  const norm = Math.sqrt(sliced.reduce((sum, v) => sum + v * v, 0));
  if (norm === 0) return sliced;
  return sliced.map((v) => v / norm);
}

export async function embedText(
  env: Env,
  text: string,
  targetDims = 512
): Promise<number[]> {
  const result = await env.AI.run("@cf/baai/bge-large-en-v1.5", {
    text: [text],
  });

  // Workers AI returns { data: [[...floats]] }
  const fullEmbedding: number[] = result.data[0];
  return truncateAndNormalise(fullEmbedding, targetDims);
}
```

---

## Batch Re-indexing Pipeline with Queues

When migrating from the 1 024-dim index to the 512-dim index, use a Queue consumer
to re-embed and upsert in batches without hitting the Workers AI rate limit.

```typescript
// src/reindex-consumer.ts
import { embedText } from "./lib/embedding";

export interface Env {
  AI: Ai;
  VECTORIZE_512: VectorizeIndex;
  DB: D1Database;
  REINDEX_QUEUE: Queue;
}

interface ReindexMessage {
  postId: string;
  text: string;
}

export default {
  async queue(
    batch: MessageBatch<ReindexMessage>,
    env: Env
  ): Promise<void> {
    const vectors: VectorizeVector[] = [];

    await Promise.all(
      batch.messages.map(async (msg) => {
        const { postId, text } = msg.body;
        try {
          const values = await embedText(env, text, 512);
          vectors.push({
            id: postId,
            values,
            metadata: { postId, indexedAt: Date.now() },
          });
        } catch (err) {
          console.error(`[reindex] failed for ${postId}:`, err);
          msg.retry();
        }
      })
    );

    if (vectors.length > 0) {
      await env.VECTORIZE_512.upsert(vectors);

      // Mark posts as migrated in D1
      const placeholders = vectors.map(() => "?").join(",");
      await env.DB.prepare(
        `UPDATE posts SET embedding_version = 512
         WHERE id IN (${placeholders})`
      )
        .bind(...vectors.map((v) => v.id))
        .run();
    }

    batch.ackAll();
  },
};
```

---

## Query-Time Truncation (Dual-Index Transition Period)

During migration, the system must query both indexes until all posts are migrated.
Route queries to the correct index based on the post's `embedding_version`.

```typescript
// src/search.ts
export async function semanticSearch(
  env: Env,
  query: string,
  topK = 20
): Promise<string[]> {
  // Use 512-dim index once majority of corpus is migrated
  const useReducedIndex = await isReducedIndexReady(env);

  const dims = useReducedIndex ? 512 : 1024;
  const queryVec = await embedText(env, query, dims);
  const index = useReducedIndex ? env.VECTORIZE_512 : env.VECTORIZE_1024;

  const results = await index.query(queryVec, {
    topK,
    returnMetadata: "none",
  });

  return results.matches.map((m) => m.id);
}

async function isReducedIndexReady(env: Env): Promise<boolean> {
  const row = await env.DB.prepare(
    "SELECT COUNT(*) as total, SUM(CASE WHEN embedding_version = 512 THEN 1 ELSE 0 END) as migrated FROM posts"
  ).first<{ total: number; migrated: number }>();
  // Switch over once 95% of posts have been migrated
  return row !== null && row.migrated / row.total >= 0.95;
}
```

---

## Int8 Quantisation on Top of Truncation

Cloudflare Vectorize supports `int8` quantisation at the index level. To use it,
create the index with `quantization: "int8"`. Vectors are still uploaded as float32;
Vectorize quantises them automatically on ingest.

```bash
# wrangler CLI (Vectorize v2)
wrangler vectorize create example project-posts-512-int8 \
  --dimensions=512 \
  --metric=cosine \
  --quantization=int8
```

Resulting storage: 512 dims × 1 byte (int8) = 512 bytes/vector vs.
original 1 024 dims × 4 bytes = 4 096 bytes/vector — an 8× reduction.

---

## Quality Validation: Recall@10 Comparison

```typescript
// scripts/validate-recall.ts
// Compares recall@10 between 1024-f32 and 512-int8 indexes
// on a labelled test set of 500 query/relevant-set pairs.

async function compareRecall(
  env: Env,
  testQueries: Array<{ query: string; relevantPostIds: string[] }>
) {
  let recall1024 = 0;
  let recall512 = 0;

  for (const { query, relevantPostIds } of testQueries) {
    const vec1024 = await embedText(env, query, 1024);
    const vec512 = await embedText(env, query, 512);

    const [r1024, r512] = await Promise.all([
      env.VECTORIZE_1024.query(vec1024, { topK: 10 }),
      env.VECTORIZE_512.query(vec512, { topK: 10 }),
    ]);

    const ids1024 = new Set(r1024.matches.map((m) => m.id));
    const ids512 = new Set(r512.matches.map((m) => m.id));
    const relevant = new Set(relevantPostIds);

    const intersection = (ids: Set<string>) =>
      [...ids].filter((id) => relevant.has(id)).length;

    recall1024 += intersection(ids1024) / relevantPostIds.length;
    recall512 += intersection(ids512) / relevantPostIds.length;
  }

  console.log({
    "Recall@10 (1024-f32)": (recall1024 / testQueries.length).toFixed(4),
    "Recall@10 (512-int8)": (recall512 / testQueries.length).toFixed(4),
  });
}
```

Typical result with `bge-large` + MRL-512 + int8: Recall@10 drops from 0.91 to 0.87
(~4.4%), which is acceptable for feed ranking but may be too lossy for primary search.
Use 512-f32 if precision matters more than storage.

---

## Anti-patterns

- **Truncating a non-MRL model** — truncation on a standard model degrades quality
  catastrophically (Recall@10 can drop below 0.5). Verify the model documentation
  explicitly states MRL support before truncating.
- **Forgetting to re-normalise after truncation** — cosine similarity requires
  unit-norm vectors. A truncated vector is no longer unit-norm; skipping normalisation
  silently produces wrong similarity scores.
- **Using int8 index without evaluating your specific query distribution** — int8
  quantisation hurts more on queries that span many rare topics. Always validate
  recall on a representative query sample before switching production traffic.
- **Deleting the full-dimension index before migration is complete** — maintain both
  indexes in parallel during the transition window.

---

## Gotchas

- Vectorize `int8` quantisation is applied server-side; you still upsert float32
  vectors from your Worker. Do not pre-quantise to int8 in application code.
- The `dimensions` property of a Vectorize index is immutable after creation. There
  is no in-place migration; you must create a new index and re-index the corpus.
- `bge-large-en-v1.5` from Workers AI returns 1 024 dims regardless of the target
  dimension — truncation happens client-side.
- ANN index quality (HNSW parameters) is unaffected by dimension reduction; you may
  need to re-tune `ef_search` if your query latency SLO changes after migration.

---

## Verification

1. Upsert 1 000 posts into both the 1 024-f32 and 512-int8 indexes.
2. Run `validateRecall` on your test query set; accept if Recall@10 degradation < 5%.
3. Compare index storage via `wrangler vectorize info <index-name>`.
4. Run a latency microbenchmark: 512-dim queries should be 15–30% faster than
   1 024-dim queries on the same `topK`.
5. Confirm `embedding_version = 512` propagates to 100% of rows in `posts` after
   the re-indexing Queue drains.

---

## Related

- `matryoshka-embeddings-mrl.md`
- `vectorize-approximate-nearest-neighbor-tuning.md`
- `vectorize-batch-upsert-incremental-sync.md`
- `vectorize-index-lifecycle-management.md`
- `embedding-model-migration.md`

---

## Sources

- BGE MRL documentation: https://huggingface.co/BAAI/bge-large-en-v1.5
- Cloudflare Vectorize index configuration: https://developers.cloudflare.com/vectorize/reference/configuration/
- Vectorize quantisation options: https://developers.cloudflare.com/vectorize/reference/index-configuration/
- Matryoshka Representation Learning paper: https://arxiv.org/abs/2205.13147
