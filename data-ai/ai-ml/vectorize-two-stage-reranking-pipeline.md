# Vectorize Two-Stage Retrieval with Cross-Encoder Reranking

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project's semantic search over public posts returns plausible-looking results but
with poor precision at rank 1–3: highly related but older or lower-quality posts
outrank fresher, more relevant ones because the ANN phase scores purely on embedding
cosine similarity with no quality signal. Additionally, posts with highly specific
vocabulary (e.g. technical slang, platform-specific memes) score low because the
embedding model averages sub-word meaning.

Goal: implement a two-stage retrieval pipeline where:
- Stage 1 (recall): Vectorize ANN retrieves the top 50 candidates cheaply
- Stage 2 (precision): a cross-encoder reranker re-scores the 50 candidates and
  reorders them, returning the top 10 with much higher precision

This pattern is standard in production RAG and semantic search systems; the cost
of running a cross-encoder on 50 pairs (~200–400 ms) is acceptable for search but
not for feed ranking at high QPS (use reranking only for explicit search queries).

---

## Context

**Stage 1 — Bi-encoder / ANN (Vectorize)**: Embeddings of query and documents are
pre-computed independently. Similarity is measured by dot-product or cosine of the
vectors. Fast O(log N) ANN lookup, but the independence assumption loses cross-
attention signal between query and document tokens.

**Stage 2 — Cross-encoder (Workers AI)**: The query and each candidate document are
concatenated and passed through a classification model that produces a relevance
score. The model attends to both texts jointly, capturing precise relevance signals.
Slow (linear in candidate count), so applied only to the top-K ANN results.

Cloudflare Workers AI exposes cross-encoder models under the text-classification
task type. `@cf/cross-encoder/ms-marco-MiniLM-L-6-v2` (MS-MARCO fine-tuned) is
well-suited for passage-level relevance scoring.

---

## Stage 1: Vectorize ANN Retrieval

```typescript
// src/search/stage1-ann.ts
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  POSTS_VECTORIZE: VectorizeIndex;
}

export interface AnnCandidate {
  postId: string;
  text: string;
  score: number;           // cosine similarity from ANN
  metadata: Record<string, unknown>;
}

/**
 * Retrieve top `recall` candidates from Vectorize ANN.
 * A larger recall window (e.g. 50) feeds the reranker with enough material.
 */
export async function annRetrieve(
  env: Env,
  queryText: string,
  recall = 50
): Promise<AnnCandidate[]> {
  const embedding = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [queryText],
  });
  const queryVec: number[] = embedding.data[0];

  const results = await env.POSTS_VECTORIZE.query(queryVec, {
    topK: recall,
    returnMetadata: "all",
  });

  return results.matches.map((m) => ({
    postId: m.id,
    text: (m.metadata?.text as string) ?? "",
    score: m.score,
    metadata: (m.metadata ?? {}) as Record<string, unknown>,
  }));
}
```

---

## Stage 2: Cross-Encoder Reranking

```typescript
// src/search/stage2-rerank.ts
export interface Env {
  AI: Ai;
}

export interface RankedResult {
  postId: string;
  text: string;
  annScore: number;
  rerankerScore: number;
  metadata: Record<string, unknown>;
}

/**
 * Re-score ANN candidates using a cross-encoder model.
 * Returns candidates sorted by reranker score, descending.
 */
export async function crossEncoderRerank(
  env: Env,
  query: string,
  candidates: Array<{ postId: string; text: string; score: number; metadata: Record<string, unknown> }>,
  topK = 10
): Promise<RankedResult[]> {
  // Cross-encoder expects [query, passage] pairs.
  // We batch all pairs into a single Workers AI call.
  const pairs = candidates.map((c) => ({
    query,
    passage: c.text.slice(0, 512), // truncate to model limit
  }));

  // Workers AI returns an array of scores in the same order as pairs.
  const scores: number[] = await env.AI.run(
    "@cf/cross-encoder/ms-marco-MiniLM-L-6-v2",
    { pairs }
  );

  const ranked: RankedResult[] = candidates.map((c, i) => ({
    postId: c.postId,
    text: c.text,
    annScore: c.score,
    rerankerScore: scores[i],
    metadata: c.metadata,
  }));

  // Sort by reranker score descending; return top-K
  return ranked
    .sort((a, b) => b.rerankerScore - a.rerankerScore)
    .slice(0, topK);
}
```

---

## Combined Pipeline

```typescript
// src/search/pipeline.ts
import { annRetrieve } from "./stage1-ann";
import { crossEncoderRerank, RankedResult } from "./stage2-rerank";

export interface Env {
  AI: Ai;
  POSTS_VECTORIZE: VectorizeIndex;
  DB: D1Database;
}

interface SearchOptions {
  query: string;
  annRecall?: number;   // how many candidates ANN retrieves (default 50)
  finalTopK?: number;   // how many results to return after reranking (default 10)
}

export async function twoStageSearch(
  env: Env,
  opts: SearchOptions
): Promise<RankedResult[]> {
  const { query, annRecall = 50, finalTopK = 10 } = opts;

  // Stage 1: ANN over Vectorize (fast, ~20–40 ms)
  const candidates = await annRetrieve(env, query, annRecall);

  if (candidates.length === 0) {
    return [];
  }

  // Fetch missing text from D1 if not stored in Vectorize metadata
  const withText = await hydrateTexts(env, candidates);

  // Stage 2: Cross-encoder reranking (slower, ~150–350 ms for 50 pairs)
  const ranked = await crossEncoderRerank(env, query, withText, finalTopK);

  return ranked;
}

async function hydrateTexts(
  env: Env,
  candidates: Array<{ postId: string; text: string; score: number; metadata: Record<string, unknown> }>
) {
  // Find candidates without text in metadata
  const missing = candidates.filter((c) => !c.text);
  if (missing.length === 0) return candidates;

  const placeholders = missing.map(() => "?").join(",");
  const rows = await env.DB.prepare(
    `SELECT id, body FROM posts WHERE id IN (${placeholders})`
  )
    .bind(...missing.map((c) => c.postId))
    .all<{ id: string; body: string }>();

  const textMap = new Map(rows.results.map((r) => [r.id, r.body]));
  return candidates.map((c) => ({
    ...c,
    text: c.text || textMap.get(c.postId) || "",
  }));
}
```

---

## Worker Entry Point

```typescript
// src/index.ts
import { twoStageSearch } from "./search/pipeline";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/search")) {
      return new Response("Not found", { status: 404 });
    }

    const query = url.searchParams.get("q");
    if (!query?.trim()) {
      return Response.json({ error: "Missing query parameter 'q'" }, { status: 400 });
    }

    const annRecall = Math.min(
      parseInt(url.searchParams.get("recall") ?? "50", 10),
      100
    );
    const topK = Math.min(
      parseInt(url.searchParams.get("topK") ?? "10", 10),
      20
    );

    const results = await twoStageSearch(env, { query, annRecall, finalTopK: topK });

    return Response.json({
      query,
      count: results.length,
      results: results.map((r) => ({
        postId: r.postId,
        text: r.text,
        rerankerScore: r.rerankerScore,
        annScore: r.annScore,
        metadata: r.metadata,
      })),
    });
  },
};
```

---

## Latency Budget

```
Stage 1 ANN (Vectorize, topK=50):    20–40 ms
Stage 2 Cross-Encoder (50 pairs):   150–350 ms
D1 text hydration (if needed):       10–30 ms
Total:                              180–420 ms
```

For the example project anonymous search use-case this is acceptable. For high-QPS feed
ranking, pre-compute reranker scores offline via a Queues consumer and cache results
in KV with a 60-second TTL.

---

## Score Fusion Alternative (Hybrid Reranking)

When you have additional signals (recency, engagement score), fuse them with the
cross-encoder score instead of using the reranker alone:

```typescript
export function reciprocalRankFusion(
  results: RankedResult[],
  recencyWeight = 0.2,
  rerankerWeight = 0.8,
  k = 60
): RankedResult[] {
  const maxAgeMs = 7 * 24 * 3600 * 1000; // 7 days

  return results
    .map((r) => {
      const ageMs = Date.now() - ((r.metadata.createdAt as number) ?? 0);
      const recencyScore = Math.max(0, 1 - ageMs / maxAgeMs);
      const fusedScore =
        rerankerWeight * r.rerankerScore +
        recencyWeight * recencyScore;
      return { ...r, rerankerScore: fusedScore };
    })
    .sort((a, b) => b.rerankerScore - a.rerankerScore);
}
```

---

## Anti-patterns

- **Calling the cross-encoder on the full corpus** — a cross-encoder on 100 K
  documents would take minutes. Always pair it with ANN recall (Stage 1 first).
- **Using the cross-encoder as a binary classifier** (is this relevant: yes/no) — the
  model outputs a continuous logit score; threshold classification throws away ranking
  information. Always sort by the raw score.
- **Storing full post text in Vectorize metadata** — Vectorize metadata has a 10 KB
  per-vector limit. Store only short excerpts (first 300 chars) in metadata; fetch
  full text from D1 for reranking.
- **Re-embedding the query twice** (once for ANN, once for something else) — embed
  the query once, cache the vector for the duration of the request.
- **Ignoring the ANN score entirely** — the ANN score is a useful signal for the rare
  case where the cross-encoder is inconsistent. Consider keeping it as a tiebreaker.

---

## Gotchas

- `@cf/cross-encoder/ms-marco-MiniLM-L-6-v2` is trained on MS-MARCO passage ranking
  (web search queries vs. ~100-word passages). Performance degrades on very short
  texts (<10 words) or very long texts (>200 words). Truncate candidates to 200 words.
- The model outputs raw logits, not normalised probabilities. Logits are comparable
  within a single batch but are NOT comparable across separate `AI.run()` calls
  (different normalisation can shift the logit range). Always sort within a single
  batch response.
- Workers AI has a concurrent inference limit per account. For high-traffic search,
  implement a semaphore in a Durable Object to queue cross-encoder calls rather than
  letting them all hit the limit simultaneously.
- Vectorize ANN `topK` is capped at 100. If your corpus is very large and you need
  Stage 2 to see more candidates, use metadata pre-filtering in Stage 1 to narrow the
  population before ANN, rather than increasing `topK` beyond 100.

---

## Verification

1. Run a set of 20 test queries with known ground-truth relevant posts.
2. Compute `Precision@3` for Stage 1 (ANN only) and Stage 2 (ANN + reranker); confirm
   reranker improves Precision@3 by at least 10 percentage points.
3. Measure end-to-end latency under load (50 concurrent search requests); confirm
   P95 < 500 ms.
4. Confirm that for queries with known relevant posts outside the top-10 ANN results,
   those posts appear in Stage 2 results (the reranker can only reorder the Stage 1
   recall window — check recall is large enough).
5. Validate `postId` values in search results resolve to actual posts in D1.

---

## Related

- `rag-reranking.md`
- `workers-ai-reranker-cross-encoder-passage-scoring.md`
- `vectorize-approximate-nearest-neighbor-tuning.md`
- `vectorize-hybrid-bm25-dense-retrieval-workers.md`
- `rag-hybrid-search.md`

---

## Sources

- Cloudflare Vectorize query API: https://developers.cloudflare.com/vectorize/reference/client-api/
- Workers AI cross-encoder models: https://developers.cloudflare.com/workers-ai/models/
- MS-MARCO MiniLM cross-encoder: https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2
- Bi-encoder vs cross-encoder comparison: https://www.sbert.net/examples/applications/cross-encoder/README.html
