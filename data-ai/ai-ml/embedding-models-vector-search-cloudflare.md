# embedding-models-vector-search-cloudflare

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Semantic search returns irrelevant results, or queries that should
match nearby chunks miss completely. Cosine scores cluster near
1.0 with no useful discrimination. Re-ranking a 1 536-dim index
over 5 M documents takes 400 ms at the edge and times out inside
a Cloudflare Worker.

## Context

Text embedding maps strings to dense vectors so semantically
similar strings land close in vector space. Model choice,
dimensionality, chunking, and similarity metric together
determine retrieval quality. Cloudflare Vectorize is the native
edge vector store — no egress, billed per stored vector, and
callable from the same Worker that generated the embedding.
Hybrid search (BM25 + vector) outperforms either alone.

## 1  Embedding model selection

| Model | Dims | Max tokens | Notes |
|-------|------|-----------|-------|
| `@cf/baai/bge-base-en-v1.5` | 768 | 512 | Best CF Workers AI default |
| `@cf/baai/bge-large-en-v1.5` | 1 024 | 512 | Higher accuracy, 2× cost |
| `text-embedding-3-small` | 1 536 (trunc. to 512) | 8 191 | OpenAI; MRL-truncatable |
| `text-embedding-3-large` | 3 072 (trunc. to 256) | 8 191 | OpenAI; expensive |
| `intfloat/e5-large-v2` | 1 024 | 512 | Strong on MTEB; self-host |

Decision guide:
- Edge / Workers AI: `bge-base-en-v1.5` (768 dims, free quota).
- Multi-lingual corpus: `multilingual-e5-large` (1 024 dims).
- Maximum recall on English: `text-embedding-3-large` truncated
  to 1 024 dims via Matryoshka representation.

## 2  Cloudflare Vectorize — setup and query

```typescript
// wrangler.toml
// [[vectorize]]
// binding = "VECTORIZE"
// index_name = "docs-768"
// dimensions = 768
// metric = "cosine"

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { query } = await req.json<{ query: string }>();

    // Generate embedding with Workers AI (same DC, zero egress)
    const { data } = await env.AI.run(
      "@cf/baai/bge-base-en-v1.5",
      { text: [query] },
    );
    const vector = data[0] as number[];  // 768 floats

    // Query top-10 with metadata
    const results = await env.VECTORIZE.query(vector, {
      topK: 10,
      returnMetadata: "all",
    });

    return Response.json(results.matches);
  },
};
```

## 3  Chunking strategies

```typescript
// Fixed-size with overlap (baseline)
function chunkFixed(
  text: string,
  size = 400,
  overlap = 80,
): string[] {
  const words = text.split(/\s+/);
  const chunks: string[] = [];
  for (let i = 0; i < words.length; i += size - overlap) {
    chunks.push(words.slice(i, i + size).join(" "));
  }
  return chunks;
}

// Recursive character splitter (prefer semantic boundaries)
// Split on "\n\n", then "\n", then ". ", then " "
function chunkRecursive(
  text: string,
  maxLen = 400,
  seps = ["\n\n", "\n", ". ", " "],
): string[] {
  for (const sep of seps) {
    if (text.length <= maxLen) return [text];
    const parts = text.split(sep);
    if (parts.length > 1) {
      return parts.flatMap((p) => chunkRecursive(p, maxLen, seps));
    }
  }
  return [text.slice(0, maxLen)];
}
```

Rule of thumb: chunk to ≤ model's max token limit (512 for BGE),
use 10–20 % overlap so a sentence split across a boundary is
still retrievable from either chunk.

## 4  Cosine vs dot product

```
Cosine similarity:   sim(a, b) = (a·b) / (‖a‖ · ‖b‖)
Dot product:         sim(a, b) = a·b

If vectors are L2-normalised:  cosine == dot product.
```

Cloudflare Vectorize supports `cosine`, `euclidean`, and
`dot-product`. Always L2-normalise embeddings at insert time
when using dot product (faster on hardware); skip normalisation
only if magnitude carries meaning (e.g., document length signal).

```typescript
function l2Normalize(v: number[]): number[] {
  const norm = Math.sqrt(v.reduce((s, x) => s + x * x, 0));
  return v.map((x) => x / (norm || 1e-9));
}
```

## 5  Hybrid search (BM25 + vector)

```typescript
// Reciprocal Rank Fusion — combine BM25 ranks and vector ranks
function rrf(
  bm25Ids: string[],
  vectorIds: string[],
  k = 60,
): string[] {
  const scores = new Map<string, number>();
  const add = (ids: string[]) =>
    ids.forEach((id, rank) => {
      scores.set(id, (scores.get(id) ?? 0) + 1 / (k + rank + 1));
    });
  add(bm25Ids);
  add(vectorIds);
  return [...scores.entries()]
    .sort(([, a], [, b]) => b - a)
    .map(([id]) => id);
}
```

BM25 via D1 `fts5` provides keyword recall; RRF fuses ranks
without needing calibrated score scales.

## Anti-patterns

- Using a model fine-tuned on one domain (code) for another
  (legal text) — embeddings become meaningless.
- Storing raw 3 072-dim vectors when 512-dim MRL truncation
  loses < 2 % recall — wastes Vectorize quota and query time.
- Chunking by character count without respecting sentence
  boundaries — splits mid-sentence degrade retrieval.
- Skipping L2 normalisation when using dot-product metric —
  long documents score higher simply due to magnitude.

## Gotchas

- Cloudflare Vectorize free plan caps at 200 k vectors and
  1 000 queries/day; paid plan raises to 5 M vectors.
- BGE models prepend "query: " or "passage: " to inputs;
  skipping the prefix degrades recall by 5–15 %.
- Vectorize only supports one metric per index; create
  separate indexes if you need both cosine and dot-product.
- Metadata filtering requires `returnMetadata` to be set;
  filtered queries are more expensive than unfiltered ones.

## Verification

- Embed 20 query/document pairs with known relevance labels;
  confirm cosine scores rank positives above negatives.
- Insert 1 000 test vectors; run a known query; assert the
  ground-truth chunk appears in top-3 results.

## Related

- `ai-ml/cloudflare-vectorize-patterns.md`
- `ai-ml/embedding-generation-patterns.md`
- `ai-ml/matryoshka-embeddings-mrl.md`
- `ai-ml/metadata-filtering-vectors.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/vectorize/
- https://developers.cloudflare.com/workers-ai/models/
- https://huggingface.co/BAAI/bge-base-en-v1.5
- https://platform.openai.com/docs/guides/embeddings
- https://www.sbert.net/docs/pretrained_models.html
