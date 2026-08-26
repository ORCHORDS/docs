# Vectorize Approximate Nearest Neighbor Tuning

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project semantic search and content recommendation queries against Vectorize return results that are either too slow (high-recall mode) or miss obviously relevant posts (low-recall mode). Tuning the ANN index parameters and query-time `topK` / `ef` settings is required to hit the platform's 50 ms p99 SLA while maintaining acceptable recall.

## Context

Cloudflare Vectorize uses an HNSW (Hierarchical Navigable Small World) graph as its approximate nearest-neighbour index. HNSW exposes two construction-time parameters — `m` (number of bi-directional links per node) and `ef_construction` (search beam width during build) — and one query-time parameter `ef` (the exploration factor at query time). Getting these right for the post-embedding corpus (~10 M 768-d vectors on example.com) determines whether the index sits in the 0.92 or 0.99 recall band.

## Architecture — HNSW Parameter Space

HNSW trades build time and memory against query-time recall and latency. At query time, a higher `ef` means more candidate nodes are explored before the top-K result set is finalized. For example project's use-cases:

| Use-case | Required recall | Acceptable p99 | Recommended ef |
|---|---|---|---|
| Semantic search (active user) | 0.95 | 80 ms | 128 |
| Feed recommendation (background) | 0.90 | 200 ms | 64 |
| Duplicate detection (write path) | 0.98 | 150 ms | 256 |
| Safety similar-content lookup | 0.85 | 40 ms | 32 |

```typescript
// vectorize-config.ts
export const QUERY_PROFILES = {
  search: { topK: 20, ef: 128 },
  feed:   { topK: 50, ef: 64  },
  dedup:  { topK: 5,  ef: 256 },
  safety: { topK: 3,  ef: 32  },
} as const;

export type QueryProfile = keyof typeof QUERY_PROFILES;
```

## Implementation — Profile-Driven Query Wrapper

A thin wrapper selects the correct profile at call time based on the originating use-case, then passes the right parameters to `vectorize.query`. Note that Vectorize's API accepts `topK` directly; `ef` is supplied via the `options` field when the index tier supports it.

```typescript
// vectorize-query.ts
import type { VectorizeIndex, VectorizeVector } from '@cloudflare/workers-types';
import { QUERY_PROFILES, QueryProfile } from './vectorize-config';

export interface SearchHit {
  id: string;
  score: number;
  metadata?: Record<string, string | number | boolean>;
}

export async function profiledQuery(
  index: VectorizeIndex,
  vector: number[],
  profile: QueryProfile,
  filter?: Record<string, string | number | boolean>,
): Promise<SearchHit[]> {
  const { topK } = QUERY_PROFILES[profile];

  const results = await index.query(vector, {
    topK,
    returnMetadata: 'indexed',
    ...(filter ? { filter } : {}),
  });

  return results.matches.map(m => ({
    id: m.id,
    score: m.score,
    metadata: m.metadata as Record<string, string | number | boolean> | undefined,
  }));
}
```

## Implementation — Recall Benchmarking Script

Run this offline against a fixed ground-truth dataset to measure actual recall at different `topK` values before changing production index parameters.

```typescript
// benchmark-recall.ts
// Run with: npx tsx benchmark-recall.ts
import { VectorizeIndex } from '@cloudflare/workers-types';

interface GroundTruth {
  queryId: string;
  queryVector: number[];
  exactNeighborIds: string[]; // from brute-force search on a sample
}

export async function measureRecall(
  index: VectorizeIndex,
  groundTruth: GroundTruth[],
  topK: number,
): Promise<{ recall: number; p50Ms: number; p99Ms: number }> {
  const latencies: number[] = [];
  let totalHits = 0;
  let totalExpected = 0;

  for (const gt of groundTruth) {
    const start = Date.now();
    const results = await index.query(gt.queryVector, { topK, returnMetadata: 'none' });
    latencies.push(Date.now() - start);

    const returned = new Set(results.matches.map(m => m.id));
    const hits = gt.exactNeighborIds.slice(0, topK).filter(id => returned.has(id)).length;
    totalHits += hits;
    totalExpected += Math.min(topK, gt.exactNeighborIds.length);
  }

  latencies.sort((a, b) => a - b);
  const p50Ms = latencies[Math.floor(latencies.length * 0.5)];
  const p99Ms = latencies[Math.floor(latencies.length * 0.99)];

  return { recall: totalHits / totalExpected, p50Ms, p99Ms };
}
```

## Optimization — Score Threshold Filtering

Returning all `topK` results regardless of similarity score pollutes the recommendation list with weakly-related content. Apply a minimum cosine similarity threshold post-query to keep only high-confidence neighbours.

```typescript
// threshold-filter.ts
const SCORE_THRESHOLDS: Record<QueryProfile, number> = {
  search: 0.78,
  feed:   0.65,
  dedup:  0.90,
  safety: 0.80,
};

export function applyScoreThreshold(
  hits: SearchHit[],
  profile: QueryProfile,
): SearchHit[] {
  const min = SCORE_THRESHOLDS[profile];
  return hits.filter(h => h.score >= min);
}
```

## Monitoring — P99 Latency Tracking in Analytics Engine

Emit per-profile latencies so the team can detect when a growing index pushes query latencies past SLA thresholds, at which point the index needs a rebuild with a higher `m` value.

```typescript
// ann-telemetry.ts
export function emitQueryMetric(
  ae: AnalyticsEngineDataset,
  profile: QueryProfile,
  latencyMs: number,
  hitCount: number,
  filteredOut: number,
): void {
  ae.writeDataPoint({
    blobs: [profile],
    doubles: [latencyMs, hitCount, filteredOut],
    indexes: [profile],
  });
}

// Alert: if P99(latencyMs) > 150 ms for 'search' profile over 5 min window,
// trigger index rebuild evaluation.
```

## Anti-patterns

- Requesting `topK: 200` for every query "to be safe" — higher `topK` increases the ANN exploration depth and inflates latency non-linearly; use the per-profile values above.
- Using the same index for both 768-d content vectors and 128-d user taste vectors — dimensions must match at index creation; use separate indexes per embedding model.
- Rebuilding the index during peak traffic — Vectorize rebuilds are eventually consistent but can temporarily degrade query latency by 2–3×; schedule rebuilds during off-peak hours.
- Applying `filter` on metadata keys that are not in the index's `metadata_config.indexed` list — unindexed filters fall back to post-query scan and eliminate most of the ANN speedup.
- Tuning `topK` at the embedding model level instead of the query level — the embedding model dimension is fixed at index creation; only query parameters are tunable without a full reindex.

## Gotchas

- Vectorize cosine similarity scores are in the range [0, 1] after normalization; dot product scores are unbounded if vectors are not unit-normalized — confirm which distance metric the index was created with via `wrangler vectorize info <index-name>`.
- `returnMetadata: 'all'` doubles query latency on large indexes; use `returnMetadata: 'indexed'` for keys declared in `metadata_config.indexed` only.
- Vectorize's free tier caps at 30 M vector dimensions (not vector count) — a 768-d index holds ~39 K vectors before hitting the limit; production example project indexes must be on a paid plan.
- Index IDs in Vectorize must be globally unique strings ≤ 64 chars; use namespaced IDs like `post:uuid` and `session:hash` to avoid collisions between entity types stored in the same index.
- HNSW graph queries are non-deterministic at equivalent `topK` and `ef` values between index versions — do not diff raw result sets between deploys; compare recall metrics over a fixed benchmark set instead.

## Verification

```bash
# Create index with explicit distance metric
wrangler vectorize create example project-posts \
  --dimensions=768 \
  --metric=cosine \
  --metadata-config='{"indexed":["type","category","createdDay"]}'

# Query and measure round-trip time
time wrangler vectorize query example project-posts \
  --vector="[$(python3 -c "import random; print(','.join(str(random.random()) for _ in range(768)))" )" \
  --top-k=20

# Confirm p99 latency via Analytics Engine
# SELECT percentile(latencyMs, 99) FROM ann_query_metrics
# WHERE profile = 'search' AND timestamp > NOW() - INTERVAL '1' HOUR
```

## Related

- `documentation/categories/ai-ml/vectorize-user-embedding-collaborative-filtering.md`
- `documentation/categories/ai-ml/vectorize-metadata-filtering-complex-predicates.md`
- `documentation/categories/ai-ml/vector-index-ann-algorithms.md`
- `documentation/categories/ai-ml/similarity-threshold-tuning.md`
- `documentation/categories/ai-ml/vectorize-ann-index-rebuild-zero-downtime.md`

## Sources

- https://developers.cloudflare.com/vectorize/reference/create-index/
- https://developers.cloudflare.com/vectorize/best-practices/query-vectors/
- https://developers.cloudflare.com/vectorize/reference/client-api/
- https://arxiv.org/abs/1603.09320  (HNSW original paper — Malkov & Yashunin 2016)
