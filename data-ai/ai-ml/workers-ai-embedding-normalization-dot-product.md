# Workers AI Embedding Normalization for Dot-Product Search

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Vectorize similarity scores vary wildly between documents of different lengths even though the
content is semantically close. Or you switch Vectorize distance metric from `cosine` to `dotProduct`
to gain speed but results degrade. Embeddings from Workers AI models are not always unit-normalised
by default, and dot-product similarity requires unit-norm vectors to be mathematically equivalent
to cosine similarity. This article covers when and how to L2-normalise embeddings in TypeScript
before upserting into Vectorize.

## Context

Cosine similarity between two vectors is defined as the dot product of their L2-normalised forms:

```
cos(a, b) = (a · b) / (||a|| * ||b||)
```

If vectors are already unit-length (||a|| = 1), cosine and dot product give the same ranking.
Vectorize supports three distance metrics: `cosine`, `dotProduct`, and `euclidean`. The `dotProduct`
metric is computed faster on Cloudflare's infrastructure but assumes the caller has pre-normalised
the vectors. Using `dotProduct` on raw unnormalised embeddings from Workers AI produces incorrect
similarity rankings because document length and token frequency inflate magnitudes.

Models to check:
- `@cf/baai/bge-large-en-v1.5` — outputs **normalised** vectors (Euclidean norm ≈ 1.0). Safe to
  use with `dotProduct` directly.
- `@cf/baai/bge-base-en-v1.5` — outputs **normalised** vectors.
- `@cf/baai/bge-small-en-v1.5` — outputs **normalised** vectors.
- `@hf/sentence-transformers/all-minilm-l6-v2` — outputs normalised vectors.
- Custom fine-tuned or LoRA-modified embedding models — **must be verified**; normalisation is not
  guaranteed.

Even for models that claim to normalise, numerical drift (float32 precision) can push ||v|| to
1.0003. Explicit normalisation before upsert is defensive and adds < 1 ms per batch.

## L2 Normalisation Utility

```typescript
// src/embeddings/normalize.ts

/**
 * Return the L2 norm (Euclidean length) of a vector.
 */
export function l2Norm(v: number[]): number {
  return Math.sqrt(v.reduce((sum, x) => sum + x * x, 0));
}

/**
 * Return a unit-length copy of v. Throws if v is a zero vector.
 */
export function normalize(v: number[]): number[] {
  const norm = l2Norm(v);
  if (norm === 0) throw new Error("Cannot normalise zero vector");
  return v.map((x) => x / norm);
}

/**
 * Normalise a batch of embeddings in-place.
 * Mutates the input array for memory efficiency on large batches.
 */
export function normalizeBatch(embeddings: number[][]): number[][] {
  for (let i = 0; i < embeddings.length; i++) {
    embeddings[i] = normalize(embeddings[i]);
  }
  return embeddings;
}

/**
 * Verify that all vectors in a batch are approximately unit-length.
 * Useful in CI / integration tests.
 */
export function assertNormalized(
  embeddings: number[][],
  tolerance = 1e-5
): void {
  for (let i = 0; i < embeddings.length; i++) {
    const norm = l2Norm(embeddings[i]);
    if (Math.abs(norm - 1.0) > tolerance) {
      throw new Error(
        `Vector at index ${i} has norm ${norm.toFixed(6)}, expected 1.0 ± ${tolerance}`
      );
    }
  }
}
```

## Generating and Normalising Embeddings

```typescript
// src/embeddings/generate.ts
import { normalize } from "./normalize";

const EMBEDDING_MODEL = "@cf/baai/bge-large-en-v1.5";

export async function embedTexts(
  ai: Ai,
  texts: string[],
  forceNormalize = true
): Promise<number[][]> {
  const result = await ai.run(EMBEDDING_MODEL, { text: texts });

  // Workers AI returns { shape: [...], data: number[][] }
  let vectors: number[][] = (result as { data: number[][] }).data;

  if (forceNormalize) {
    vectors = vectors.map(normalize);
  }

  return vectors;
}
```

## Upserting Normalised Vectors into Vectorize (dotProduct index)

```typescript
// src/vectorize/upsert.ts
import { embedTexts } from "../embeddings/generate";
import { assertNormalized } from "../embeddings/normalize";

interface Document {
  id: string;
  text: string;
  metadata: Record<string, string | number | boolean>;
}

export async function upsertDocuments(
  ai: Ai,
  index: VectorizeIndex,
  documents: Document[]
): Promise<VectorizeAsyncMutation> {
  const texts = documents.map((d) => d.text);
  const vectors = await embedTexts(ai, texts, true); // force normalise

  // Defensive check — remove in production hot-paths
  if (process.env.NODE_ENV !== "production") {
    assertNormalized(vectors);
  }

  const vectorizeVectors: VectorizeVector[] = documents.map((doc, i) => ({
    id: doc.id,
    values: vectors[i],
    metadata: doc.metadata,
  }));

  return index.upsert(vectorizeVectors);
}
```

## Creating a dotProduct Index

The Vectorize index must be created with `metric: "dotProduct"` to take advantage of normalised
vectors. Switching metric on an existing index requires a full rebuild.

```bash
# Create a new index with dotProduct metric:
npx wrangler vectorize create my-dot-index \
  --dimensions 1024 \
  --metric dotProduct
```

```toml
# wrangler.toml
[[vectorize]]
binding = "MY_INDEX"
index_name = "my-dot-index"
```

## Query-Side Normalisation

The query vector must also be normalised before calling `index.query()`. A raw query vector against
a pre-normalised index still returns results, but the score magnitudes are wrong and ranking can
be affected when the query vector has non-unit norm.

```typescript
// src/vectorize/query.ts
import { embedTexts } from "../embeddings/generate";

export async function semanticSearch(
  ai: Ai,
  index: VectorizeIndex,
  queryText: string,
  topK = 10
): Promise<VectorizeMatches> {
  // embedTexts already normalises when forceNormalize=true
  const [queryVector] = await embedTexts(ai, [queryText], true);

  return index.query(queryVector, {
    topK,
    returnMetadata: "indexed",
  });
}
```

## Benchmarking Norm Distribution

Before migrating to `dotProduct`, verify that your model's output is close to unit-norm.

```typescript
// scripts/check-norms.ts
import { l2Norm } from "../src/embeddings/normalize";

async function checkNorms(ai: Ai, sampleTexts: string[]) {
  const result = await ai.run("@cf/baai/bge-large-en-v1.5", {
    text: sampleTexts,
  });
  const vectors: number[][] = (result as { data: number[][] }).data;

  const norms = vectors.map(l2Norm);
  const min = Math.min(...norms);
  const max = Math.max(...norms);
  const mean = norms.reduce((a, b) => a + b, 0) / norms.length;

  console.log({ min, max, mean, sampleSize: norms.length });
  // Expected for BGE: min ≈ 0.9998, max ≈ 1.0002, mean ≈ 1.0000
}
```

## Anti-patterns

- **Creating a `dotProduct` index and upserting unnormalised vectors** — scores compress to the
  range around magnitude², causing documents with more tokens to rank higher regardless of semantic
  relevance.
- **Normalising after storing in Vectorize** — you cannot retroactively update vector values in
  place; you must delete and re-upsert.
- **Using `cosine` metric with vectors you have already normalised** — technically still correct
  (cosine of unit vectors is the dot product), but wastes the normalisation step and slows queries
  versus `dotProduct`.
- **Normalising query text embedding but not stored embeddings (or vice versa)** — asymmetric
  normalisation breaks the equivalence and degrades ranking.

## Gotchas

- `@cf/baai/bge-large-en-v1.5` has 1024 dimensions; `@cf/baai/bge-base-en-v1.5` has 768 and
  `@cf/baai/bge-small-en-v1.5` has 384. The Vectorize index `--dimensions` must match exactly.
- Float32 precision means a "normalised" vector from the model may have norm 1.000003; the
  `assertNormalized` tolerance of `1e-5` is intentionally loose to pass these cases in tests.
- Workers AI embedding batches are limited to 100 strings per call. Split larger batches before
  calling `ai.run()`.
- Vectorize `dotProduct` scores range from –1 to +1 for normalised vectors (same as cosine). A
  score of `0.85` indicates high similarity; below `0.50` is typically noise.

## Verification

```bash
# After upserting 10 normalised documents, query and check scores are in (0.5, 1.0]:
wrangler dev --local
curl -s -X POST http://localhost:8787/search \
  -H "Content-Type: application/json" \
  -d '{"query":"machine learning model deployment"}' \
  | jq '.matches[].score'
# All scores should be ≤ 1.0 and > 0.0 for relevant results.
```

## Related

- `vectorize-dot-product-vs-cosine-similarity.md` — conceptual comparison of distance metrics
- `vectorize-approximate-nearest-neighbor-tuning.md` — ANN index parameters for dotProduct
- `embedding-generation-patterns.md` — batching and caching embedding calls
- `vectorize-cosine-similarity-threshold-tuning-workers.md` — threshold selection after choosing metric

## Sources

- Cloudflare Vectorize distance metrics: https://developers.cloudflare.com/vectorize/reference/distance-metrics/
- BGE embedding model card: https://huggingface.co/BAAI/bge-large-en-v1.5
- Workers AI embedding API: https://developers.cloudflare.com/workers-ai/models/bge-large-en-v1.5/
- Vectorize create index: https://developers.cloudflare.com/vectorize/get-started/
