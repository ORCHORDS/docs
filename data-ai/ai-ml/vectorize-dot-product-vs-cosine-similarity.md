# Vectorize Distance Metric Selection: Dot Product vs Cosine Similarity

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You are building a semantic search or RAG pipeline on Cloudflare Vectorize and need to choose between `dot-product`, `cosine`, and `euclidean` distance metrics when creating your index. The wrong metric can silently degrade search relevance by 10–30% for your embedding model, and you cannot change the metric after index creation without a full re-index.

Engineers frequently default to cosine similarity because it is the most commonly cited in documentation, but many modern embedding models — including those served by Workers AI — produce normalised unit vectors where cosine and dot-product are mathematically equivalent, making the dot-product path strictly faster.

## Context

Cloudflare Vectorize is a globally distributed vector database that runs at the edge alongside Workers. Every Vectorize index declares its metric at creation time via the `--metric` flag in Wrangler or the REST API. The platform uses approximate nearest-neighbour (ANN) indexing, so metric choice affects both the index data structure and every query execution path. Workers AI text embedding models (`@cf/baai/bge-base-en-v1.5`, `@cf/baai/bge-large-en-v1.5`, etc.) emit L2-normalised vectors by default, a property that fundamentally determines the correct metric choice.

Choosing the wrong metric does not throw an error — it silently reorders results, causing recall degradation that is invisible unless you run offline evaluation against labelled queries.

## Understanding the Three Metrics

### Cosine Similarity

Cosine similarity measures the angle between two vectors, ignoring magnitude:

```
cosine(A, B) = (A · B) / (|A| × |B|)
```

Vectorize stores the metric internally as `cosine` and normalises on query. This requires an additional division per candidate at query time. Use cosine when:

- Your pipeline may receive un-normalised embeddings from external models
- You cannot guarantee that all vectors have unit magnitude
- You are mixing embeddings from multiple models with different magnitude scales

```typescript
// wrangler.toml excerpt
[[vectorize]]
binding = "VECTORIZE"
index_name = "semantic-search"
# metric = "cosine"  # default when omitted

// Create via Wrangler CLI:
// npx wrangler vectorize create semantic-search --dimensions=768 --metric=cosine
```

### Dot Product

Dot product is the raw inner product of two vectors:

```
dot(A, B) = Σ(Aᵢ × Bᵢ)
```

When both vectors are unit-normalised (|A| = |B| = 1.0), the dot product equals the cosine similarity — but without the magnitude normalisation overhead. Workers AI embedding models produce L2-normalised output, making dot-product the correct choice for all-Workers-AI pipelines:

```typescript
// worker.ts
import { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { query } = await request.json<{ query: string }>();

    // Workers AI BGE models produce unit vectors
    const embeddingResponse = await env.AI.run(
      "@cf/baai/bge-base-en-v1.5",
      { text: [query] }
    );

    const queryVector = embeddingResponse.data[0]; // Already L2-normalised

    // With dot-product index, no normalisation penalty at query time
    const results = await env.VECTORIZE.query(queryVector, {
      topK: 10,
      returnMetadata: "all",
    });

    return Response.json(results);
  },
};
```

```bash
# Create index with dot-product metric for Workers AI embeddings
npx wrangler vectorize create my-index --dimensions=768 --metric=dot-product
```

### Euclidean (L2)

Euclidean distance measures the straight-line distance between vectors:

```
euclidean(A, B) = sqrt(Σ(Aᵢ - Bᵢ)²)
```

Use euclidean only for:
- Dense numerical feature vectors (tabular ML features)
- Image pixel embeddings where geometric distance has semantic meaning
- Situations where magnitude differences encode real signal (e.g., document frequency)

Euclidean is almost never correct for NLP text embeddings because it conflates direction with magnitude, penalising semantically-similar documents that differ in length.

## Verifying Your Embedding Model's Output Magnitude

Before choosing a metric, verify whether your embedding model emits normalised vectors:

```typescript
// verify-embedding-norm.ts  – run as a Worker or via wrangler dev
async function checkNorm(env: Env, sampleText: string): Promise<void> {
  const response = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [sampleText],
  });

  const vec = response.data[0];
  const magnitude = Math.sqrt(vec.reduce((sum, v) => sum + v * v, 0));

  console.log(`Vector dimensions: ${vec.length}`);
  console.log(`L2 magnitude: ${magnitude.toFixed(6)}`);
  // Workers AI BGE models: magnitude ≈ 1.000000 (unit vector)
  // OpenAI text-embedding-3-small: also unit vectors
  // Custom models: may vary
}
```

Expected output for Workers AI BGE models:
```
Vector dimensions: 768
L2 magnitude: 1.000000
```

## Decision Matrix

```typescript
// Metric selection helper — embed this logic in your index provisioning script
interface EmbeddingModelConfig {
  model: string;
  outputNormalised: boolean;
  dimensions: number;
  recommendedMetric: "dot-product" | "cosine" | "euclidean";
}

const WORKERS_AI_MODELS: EmbeddingModelConfig[] = [
  {
    model: "@cf/baai/bge-base-en-v1.5",
    outputNormalised: true,
    dimensions: 768,
    recommendedMetric: "dot-product",
  },
  {
    model: "@cf/baai/bge-large-en-v1.5",
    outputNormalised: true,
    dimensions: 1024,
    recommendedMetric: "dot-product",
  },
  {
    model: "@cf/baai/bge-small-en-v1.5",
    outputNormalised: true,
    dimensions: 384,
    recommendedMetric: "dot-product",
  },
];

// Matryoshka / truncated embeddings: still unit-normalised after truncation
// if you re-normalise after slicing. Without re-normalisation, use cosine.
function getMetricForTruncatedEmbedding(
  originalVector: number[],
  targetDimensions: number,
  reNormalise: boolean
): "dot-product" | "cosine" {
  if (reNormalise) {
    return "dot-product"; // you normalised, so magnitude is 1
  }
  return "cosine"; // rely on Vectorize to normalise at query time
}
```

## Migrating Between Metrics

Vectorize does not support changing the metric of an existing index. Migration requires a full re-index:

```typescript
// migration-script.ts – run via wrangler dev or a scheduled Worker
async function migrateMetric(
  env: Env & {
    OLD_INDEX: VectorizeIndex;
    NEW_INDEX: VectorizeIndex;
  }
): Promise<void> {
  const BATCH_SIZE = 500;
  let cursor: string | undefined;

  do {
    // Vectorize REST API supports listing vectors with pagination
    const listResponse = await env.OLD_INDEX.getByIds(
      await fetchNextBatch(env.OLD_INDEX, cursor, BATCH_SIZE)
    );

    const vectors = listResponse.map((v) => ({
      id: v.id,
      values: v.values,
      metadata: v.metadata,
      namespace: v.namespace,
    }));

    await env.NEW_INDEX.upsert(vectors);

    // cursor = listResponse.nextCursor;
    // Continue until no more vectors
  } while (cursor);

  console.log("Migration complete — update wrangler.toml binding and redeploy");
}
```

## Anti-patterns

- Using `cosine` for all Workers AI pipelines "to be safe" — unit-vector models gain no benefit but pay normalisation overhead on every ANN candidate evaluation
- Using `euclidean` for NLP text embeddings — magnitude encodes nothing useful for semantic similarity
- Mixing embedding models with different normalisation properties in one index and using `dot-product` — un-normalised vectors from a custom model will score incorrectly against unit vectors
- Assuming you can change the metric later without a full re-index
- Not verifying the output magnitude of third-party or fine-tuned embedding models before choosing a metric
- Using dot-product with Matryoshka-truncated vectors that were not re-normalised after truncation

## Gotchas

- The Vectorize UI and Wrangler default to `cosine` when `--metric` is omitted. For Workers AI pipelines this is functionally correct but slower than dot-product.
- Score ranges differ by metric: cosine scores are in `[-1, 1]`, dot-product scores on unit vectors are also `[-1, 1]`, but dot-product on non-unit vectors is unbounded. Never hard-code a threshold without knowing the metric.
- The Vectorize REST API returns a `score` field, not a distance. For cosine and dot-product, higher score = more similar. For euclidean, lower score = more similar.
- Namespaced queries apply the metric per-namespace, not across namespaces — cross-namespace comparisons are not supported.
- Workers AI embedding inference adds ~20–50 ms; incorrect metric choice adds at most a few ms per query, so metric correctness matters far more for recall quality than raw latency.

## Verification

```typescript
// Smoke test: identical text should score ≈ 1.0 regardless of metric
async function verifyMetricSanity(env: Env): Promise<void> {
  const text = "Cloudflare Workers AI vector search";

  const { data } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [text, text],
  });

  const [vecA, vecB] = data;

  const dotProduct = vecA.reduce((sum, v, i) => sum + v * vecB[i], 0);
  console.assert(Math.abs(dotProduct - 1.0) < 0.001, "Identical texts must score ~1.0");

  // Insert vecA, query with vecB — should return score ≈ 1.0
  await env.VECTORIZE.upsert([{ id: "test-sanity", values: vecA }]);
  const results = await env.VECTORIZE.query(vecB, { topK: 1 });
  console.assert(results.matches[0].score > 0.99, "Round-trip score must be ~1.0");
  console.log(`Metric sanity check passed. Score: ${results.matches[0].score}`);
}
```

Run this during CI or after index creation to confirm metric is behaving as expected.

## Related

- `vectorize-ann-index-rebuild-zero-downtime.md` — rebuilding index after metric migration
- `embedding-generation-patterns.md` — embedding model selection and batching
- `matryoshka-embeddings-mrl.md` — truncating MRL vectors and re-normalisation
- `vectorize-metadata-filtering-complex-predicates.md` — pre-filter and post-filter effects on ANN recall

## Sources

- Cloudflare Vectorize documentation — Index configuration: https://developers.cloudflare.com/vectorize/reference/
- Cloudflare Workers AI embedding models: https://developers.cloudflare.com/workers-ai/models/
- Johnson, J. et al. "Billion-scale similarity search with GPUs." IEEE Transactions on Big Data, 2019 — foundational paper on ANN metric selection
