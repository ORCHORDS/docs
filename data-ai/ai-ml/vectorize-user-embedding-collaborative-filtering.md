# Vectorize User Embedding Collaborative Filtering

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project needs a "you might like" feed that works even when users are anonymous and leave no explicit ratings. Collaborative filtering based on behavioural embeddings — derived from which posts a user lingers on, upvotes, or shares — surfaces relevant content without requiring a social graph or personal profile.

## Context

Cloudflare Vectorize stores dense float vectors alongside arbitrary metadata. By encoding each anonymous user's interaction history into a vector and querying Vectorize for the nearest user-neighbours, then aggregating those neighbours' top posts, the platform achieves item-based collaborative filtering entirely at the edge without an external ML inference server.

## Architecture — Embedding Strategy

Each user session accumulates a set of interaction signals. These are aggregated into a fixed-dimension behavioural vector using Workers AI's text embedding model as the backbone. The post bodies the user interacted with are concatenated and embedded to form a "taste vector" that is stored and later queried for neighbour lookup.

```typescript
// types.ts
export interface InteractionSignal {
  postId: string;
  postBody: string;
  dwellMs: number;       // milliseconds the post was in viewport
  upvoted: boolean;
  shared: boolean;
}

export interface UserEmbeddingRecord {
  sessionId: string;      // anonymous session token (hashed)
  vector: number[];       // 768-d from @cf/baai/bge-base-en-v1.5
  topPostIds: string[];   // top 20 interacted post IDs for candidate expansion
  updatedAt: number;      // Unix ms
}
```

## Implementation — Building and Upserting the Taste Vector

Interactions are weighted by signal strength: a share counts 3×, an upvote 2×, a dwell-over-10s counts 1×. The weighted post texts are concatenated (up to 512 tokens) before embedding. The result is upserted into a Vectorize index keyed by `sessionId`.

```typescript
// embed-user-taste.ts
import type { Ai, VectorizeIndex } from '@cloudflare/workers-types';

const WEIGHT_SHARE  = 3;
const WEIGHT_UPVOTE = 2;
const WEIGHT_DWELL  = 1;
const DWELL_THRESHOLD_MS = 10_000;

export async function upsertUserTasteVector(
  ai: Ai,
  vectorize: VectorizeIndex,
  sessionId: string,
  signals: InteractionSignal[],
): Promise<void> {
  // Weight and collect post texts
  const weightedTexts: string[] = [];
  const topPostIds: string[] = [];

  for (const sig of signals) {
    const weight =
      (sig.shared ? WEIGHT_SHARE : 0) +
      (sig.upvoted ? WEIGHT_UPVOTE : 0) +
      (sig.dwellMs >= DWELL_THRESHOLD_MS ? WEIGHT_DWELL : 0);

    if (weight === 0) continue;
    for (let i = 0; i < weight; i++) weightedTexts.push(sig.postBody);
    topPostIds.push(sig.postId);
  }

  if (weightedTexts.length === 0) return;

  const combined = weightedTexts.join(' ').slice(0, 2048); // token budget guard

  const { data } = await ai.run('@cf/baai/bge-base-en-v1.5', {
    text: [combined],
  }) as { data: number[][] };

  const vector = data[0];

  await vectorize.upsert([{
    id: `session:${sessionId}`,
    values: vector,
    metadata: {
      type: 'user',
      topPostIds: topPostIds.slice(0, 20).join(','),
      updatedAt: Date.now(),
    },
  }]);
}
```

## Implementation — Neighbour Lookup and Candidate Expansion

To find similar users, query Vectorize with the current user's taste vector filtered to vectors of `type: user`. Then expand the post candidate set from those neighbours' `topPostIds` metadata.

```typescript
// collaborative-filter.ts
export async function getCandidatePostIds(
  ai: Ai,
  vectorize: VectorizeIndex,
  sessionId: string,
  topK = 20,
  neighbourCount = 10,
): Promise<string[]> {
  // Retrieve the current user's vector by ID
  const existing = await vectorize.getByIds([`session:${sessionId}`]);
  if (!existing.length || !existing[0].values) return [];

  const queryVector = existing[0].values as number[];

  // Find nearest user neighbours (exclude self)
  const results = await vectorize.query(queryVector, {
    topK: neighbourCount + 1,
    filter: { type: 'user' },
    returnMetadata: 'all',
  });

  const candidates = new Set<string>();

  for (const match of results.matches) {
    if (match.id === `session:${sessionId}`) continue; // skip self

    const postIds = (match.metadata?.topPostIds as string | undefined)?.split(',') ?? [];
    for (const id of postIds) candidates.add(id);

    if (candidates.size >= topK * 5) break; // cap expansion
  }

  return [...candidates].slice(0, topK * 5);
}
```

## Optimization — Incremental Vector Updates with KV Debounce

Re-embedding on every interaction is expensive. Use KV to buffer signals for 30 seconds and batch them into a single embed+upsert call via a Durable Object alarm or Queue consumer.

```typescript
// debounce-kv.ts
export async function bufferSignal(
  kv: KVNamespace,
  sessionId: string,
  signal: InteractionSignal,
): Promise<void> {
  const key = `signals:${sessionId}`;
  const existing = await kv.get<InteractionSignal[]>(key, 'json') ?? [];
  existing.push(signal);
  // 30-second TTL; the Queue consumer drains before expiry
  await kv.put(key, JSON.stringify(existing), { expirationTtl: 60 });
}

export async function drainAndEmbed(
  kv: KVNamespace,
  ai: Ai,
  vectorize: VectorizeIndex,
  sessionId: string,
): Promise<void> {
  const key = `signals:${sessionId}`;
  const signals = await kv.get<InteractionSignal[]>(key, 'json');
  if (!signals?.length) return;

  await kv.delete(key); // optimistic delete before expensive embed
  await upsertUserTasteVector(ai, vectorize, sessionId, signals);
}
```

## Monitoring — Stale Vector Pruning

Vectorize does not auto-expire vectors. A nightly Cron Trigger prunes user vectors older than 30 days to avoid stale anonymous sessions polluting neighbour queries.

```typescript
// prune-stale-users.ts
// Scheduled: 0 3 * * *
export async function pruneStaleUserVectors(
  vectorize: VectorizeIndex,
  cutoffMs: number = 30 * 24 * 60 * 60 * 1000,
): Promise<{ pruned: number }> {
  const cutoff = Date.now() - cutoffMs;
  // Vectorize does not support range deletes by metadata — use a D1 index
  // table `user_vector_index(session_id, updated_at)` for efficient pruning.
  // This function illustrates the delete call once IDs are resolved.
  const staleIds: string[] = []; // populated from D1 query in practice
  if (staleIds.length) await vectorize.deleteByIds(staleIds);
  return { pruned: staleIds.length };
}
```

## Anti-patterns

- Embedding raw user IDs instead of behavioural content — the model has no semantics for opaque tokens.
- Using cosine similarity when all vectors are already L2-normalised by `bge-base-en-v1.5` — dot product is equivalent and faster in that case.
- Expanding candidates without deduplication — the same post can appear in many neighbours' `topPostIds`; dedup before scoring.
- Storing personal identifiers in Vectorize metadata — for anonymous users, only store hashed session tokens.
- Running neighbour queries synchronously on every feed request — cache results in KV with a 5-minute TTL.

## Gotchas

- `vectorize.getByIds` returns vectors only if `returnValues: true` was set at upsert time, or by using the `getByIds` overload that fetches from the index storage layer — verify your index config.
- Vectorize metadata values must be strings, numbers, or booleans — serialise `topPostIds` as a comma-joined string, not an array.
- `@cf/baai/bge-base-en-v1.5` outputs 768-d vectors; the Vectorize index dimensions must match exactly at creation time and cannot be changed after the fact.
- Querying with `filter: { type: 'user' }` requires the index to be created with `metadata_config: { indexed: ['type'] }` in `wrangler.toml`.
- Anonymous session churn means a large fraction of vectors are queried only once; set a short TTL strategy in D1 to avoid unbounded index growth.

## Verification

```bash
# Upsert a test user vector and verify retrieval
wrangler vectorize get-by-ids my-user-index --ids "session:test123"

# Query neighbours for the test session
curl https://api.example.com/feed/collab \
  -H "X-Session-Id: test123" | jq '.candidates | length'
# Expect >= 10 candidate post IDs
```

## Related

- `documentation/categories/ai-ml/vectorize-approximate-nearest-neighbor-tuning.md`
- `documentation/categories/ai-ml/embedding-generation-patterns.md`
- `documentation/categories/ai-ml/ai-content-recommendation-collaborative-filtering-d1.md`
- `documentation/categories/ai-ml/vectorize-multi-tenant-namespace-partitioning.md`

## Sources

- https://developers.cloudflare.com/vectorize/
- https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/
- https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
- https://developers.cloudflare.com/vectorize/best-practices/insert-vectors/
