# Vectorize Cosine Similarity Threshold Tuning Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Vectorize semantic search returns results but the quality boundary is wrong: low-
relevance documents appear in top results, or obviously relevant ones are missing because
the nearest-neighbour cutoff is too aggressive. You need a systematic method for choosing
a cosine similarity threshold for your specific corpus and query distribution, and for
applying it in a Workers handler that rejects below-threshold results.

---

## Context

Vectorize's `query()` method returns up to `topK` vectors with a `score` field. For
cosine similarity indices the score is in `[-1, 1]` (Vectorize clamps to `[0, 1]` for
normalised vectors). A raw `topK` return with no score floor includes the K nearest
neighbours regardless of how dissimilar they are — useful for exploration, wrong for
production retrieval.

**Why tuning matters:**
- The right threshold varies by embedding model, index size, domain vocabulary, and query
  type.
- A threshold calibrated on one embedding model (`@cf/baai/bge-small-en-v1.5`) will be
  wrong for another (`@cf/baai/bge-large-en-v1.5`) even on the same corpus.
- Thresholds that work at index size 10 K degrade as the index grows — nearest neighbours
  get closer and the score distribution compresses.

---

## Understanding the Vectorize Score Distribution

Before picking a number, characterise your index's score distribution. The script below
queries a sample of known relevant and known irrelevant pairs and prints their score ranges.

```typescript
// calibrate.ts — run as a one-off Worker script or wrangler dev session
interface ScoredPair {
  queryId: string;
  docId: string;
  score: number;
  label: 'relevant' | 'irrelevant';
}

export async function calibrate(
  env: Env,
  labelledPairs: ScoredPair[]
): Promise<{ suggested: number; precision: number; recall: number }> {
  // Build a score histogram for relevant vs. irrelevant pairs
  const relevant = labelledPairs.filter((p) => p.label === 'relevant').map((p) => p.score);
  const irrelevant = labelledPairs.filter((p) => p.label === 'irrelevant').map((p) => p.score);

  const mean = (arr: number[]) => arr.reduce((s, x) => s + x, 0) / arr.length;
  const min = (arr: number[]) => Math.min(...arr);

  // F1-maximising threshold sweep
  let bestF1 = 0;
  let bestThreshold = 0.5;

  for (let t = 0.3; t <= 0.99; t += 0.01) {
    const tp = relevant.filter((s) => s >= t).length;
    const fp = irrelevant.filter((s) => s >= t).length;
    const fn = relevant.filter((s) => s < t).length;

    const precision = tp / (tp + fp || 1);
    const recall = tp / (tp + fn || 1);
    const f1 = tp === 0 ? 0 : (2 * precision * recall) / (precision + recall);

    if (f1 > bestF1) {
      bestF1 = f1;
      bestThreshold = t;
    }
  }

  const tp = relevant.filter((s) => s >= bestThreshold).length;
  const fp = irrelevant.filter((s) => s >= bestThreshold).length;
  const fn = relevant.filter((s) => s < bestThreshold).length;

  return {
    suggested: Math.round(bestThreshold * 1000) / 1000,
    precision: tp / (tp + fp || 1),
    recall: tp / (tp + fn || 1),
  };
}
```

---

## Threshold Storage in KV

Store per-index thresholds so they can be updated without a redeployment.

```typescript
// thresholds.ts
export interface VectorizeThreshold {
  score: number;         // minimum cosine similarity to accept
  topK: number;          // how many candidates to fetch before filtering
  updatedAt: string;
}

const DEFAULT: VectorizeThreshold = { score: 0.72, topK: 20, updatedAt: '' };

export async function getThreshold(
  kv: KVNamespace,
  indexName: string
): Promise<VectorizeThreshold> {
  const val = await kv.get<VectorizeThreshold>(`vectorize:threshold:${indexName}`, 'json');
  return val ?? DEFAULT;
}

export async function setThreshold(
  kv: KVNamespace,
  indexName: string,
  score: number,
  topK = 20
): Promise<void> {
  await kv.put(
    `vectorize:threshold:${indexName}`,
    JSON.stringify({ score, topK, updatedAt: new Date().toISOString() }),
    { expirationTtl: 60 * 60 * 24 * 365 }
  );
}
```

---

## Retrieval Handler with Score Filtering

```typescript
// search.ts
import { getThreshold } from './thresholds';

export interface SearchResult {
  id: string;
  score: number;
  metadata?: Record<string, string | number | boolean>;
}

export async function semanticSearch(
  env: Env,
  query: string,
  indexName: string = 'main'
): Promise<SearchResult[]> {
  // 1. Embed query
  const embeddingResult = await env.AI.run('@cf/baai/bge-small-en-v1.5', {
    text: [query],
  });
  const queryVector = embeddingResult.data[0];

  // 2. Load threshold config
  const { score: minScore, topK } = await getThreshold(env.THRESHOLDS_KV, indexName);

  // 3. Query Vectorize — fetch more than needed to allow filtering
  const queryResult = await env.VECTORIZE.query(queryVector, {
    topK,
    returnMetadata: 'all',
  });

  // 4. Apply cosine threshold
  const accepted = queryResult.matches
    .filter((m) => m.score >= minScore)
    .map((m) => ({
      id: m.id,
      score: m.score,
      metadata: m.metadata as Record<string, string | number | boolean> | undefined,
    }));

  return accepted;
}
```

---

## Adaptive topK: Compensating for Compressed Score Distributions

As an index grows, score distributions compress toward higher values. Fetch more
candidates and apply the threshold, rather than raising the threshold to compensate.

```typescript
// adaptive-topk.ts
export function adaptiveTopK(indexSize: number, baseTopK = 10): number {
  // Empirical rule: for every order of magnitude in index size,
  // double the candidate set to maintain post-filter recall.
  if (indexSize < 10_000) return baseTopK;
  if (indexSize < 100_000) return baseTopK * 2;
  if (indexSize < 1_000_000) return baseTopK * 4;
  return baseTopK * 8;
}
```

---

## Logging Score Distributions for Ongoing Tuning

Write score and filter outcomes to Analytics Engine for ongoing threshold drift detection.

```typescript
// analytics.ts
export function logSearchEvent(
  ae: AnalyticsEngineDataset,
  indexName: string,
  topScore: number,
  returned: number,
  filtered: number
): void {
  ae.writeDataPoint({
    blobs: [indexName],
    doubles: [topScore, returned, filtered],
    indexes: [indexName],
  });
}
```

Query in Cloudflare Analytics to detect threshold drift:

```sql
-- Workers Analytics Engine SQL API
SELECT
  blob1 AS index_name,
  quantileWeighted(0.5)(double1)  AS p50_top_score,
  quantileWeighted(0.95)(double1) AS p95_top_score,
  avg(double3)                     AS avg_filtered,
  avg(double2)                     AS avg_returned,
  toStartOfDay(timestamp)          AS day
FROM metricsDataset
WHERE timestamp > NOW() - INTERVAL '14' DAY
GROUP BY index_name, day
ORDER BY day DESC;
```

A rising `avg_filtered` with stable `p50_top_score` indicates the threshold is too high
for current traffic; a falling `p50_top_score` suggests embedding model or corpus drift.

---

## Anti-patterns

- **Using the same threshold across different embedding models** — each model produces
  scores in a different effective range; calibrate per model.
- **Setting `topK` equal to the desired result count** — this leaves no margin for
  threshold filtering; always over-fetch (2–4× the result count) and filter.
- **Treating cosine similarity as a probability** — a score of 0.85 does not mean 85%
  relevance; it is a geometric angle metric and must be calibrated empirically.
- **Hardcoding the threshold in Worker code** — threshold tuning is an ongoing operational
  task; store in KV or a config table so adjustments do not require redeployment.

---

## Gotchas

- Vectorize uses approximate nearest-neighbour (ANN); results are not guaranteed to be
  the true global nearest neighbours. Raising `topK` to compensate for filtering reduces
  the ANN approximation error as well.
- Cosine similarity in Vectorize requires that vectors are normalised (unit length).
  `@cf/baai/bge-*` models return L2-normalised vectors by default; other models may not.
  Unnormalised vectors produce dot-product-like scores, not true cosine similarity.
- Vectorize's `score` field precision is float32. Threshold comparisons at the 4th decimal
  place (e.g. `>= 0.7231`) are unlikely to be meaningful; round thresholds to two decimal
  places.
- If your index mixes documents from different domains (e.g. legal and medical), a single
  threshold is likely wrong for both — consider per-namespace indices or metadata-based
  threshold overrides.

---

## Verification

1. Run `calibrate()` against 50 labelled query-document pairs; confirm `suggested` is
   within 0.05 of manual inspection.
2. Store the suggested threshold via `setThreshold()`; confirm `getThreshold()` returns it
   on the next request.
3. Issue a query whose correct answer has a known score > threshold; confirm it is
   returned.
4. Issue a query for which the nearest Vectorize match has a known score < threshold;
   confirm `semanticSearch` returns an empty array.
5. Query Analytics Engine after 24 h of traffic; confirm `avg_filtered` is less than 20%
   of `avg_returned` (i.e. the threshold is not over-filtering).

---

## Related

- `similarity-threshold-tuning.md`
- `vectorize-approximate-nearest-neighbor-tuning.md`
- `vectorize-dot-product-vs-cosine-similarity.md`
- `vectorize-hybrid-bm25-dense-retrieval-workers.md`
- `embedding-generation-patterns.md`
- `cloudflare-vectorize-patterns.md`

---

## Sources

- Cloudflare Vectorize: https://developers.cloudflare.com/vectorize/
- Vectorize `query()` reference: https://developers.cloudflare.com/vectorize/reference/client-api/
- Workers AI embedding models: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
