# Vectorize Query Latency Optimization

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Semantic search or recommendation features powered by Cloudflare Vectorize return results in
200–600 ms, making them too slow for real-time UI interactions. Query throughput is limited and
P99 latency spikes on cold namespaces.

## Context

Cloudflare Vectorize is a globally-distributed vector database built into the Workers platform.
Queries involve ANN (Approximate Nearest Neighbour) graph traversal inside the Vectorize
infrastructure. Latency drivers: namespace warm-up, result-set cardinality, metadata filter
selectivity, and the number of returned vectors with their full float arrays. Minimising each
reduces end-to-end time.

---

## 1. Reduce Returned Dimensions with `returnValues: false`

Returning raw vector values adds payload size and serialisation cost. Omit them unless you need
to re-rank client-side.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const query = await request.json<{ text: string }>();
    const embedding = await embed(query.text, env); // your embedding helper

    const results = await env.VECTORIZE_INDEX.query(embedding, {
      topK: 10,
      returnValues: false,       // skip float arrays – saves ~40% payload
      returnMetadata: 'indexed', // only indexed fields, not full blobs
    });

    return Response.json(results.matches);
  },
};
```

## 2. Use Metadata Filters to Shrink the Search Space

Pre-filter with indexed metadata so the ANN traversal visits fewer nodes.

```typescript
async function filteredSearch(
  embedding: number[],
  tenantId: string,
  env: Env,
) {
  // Only vectors tagged with this tenant are scored – smaller graph walk
  return env.VECTORIZE_INDEX.query(embedding, {
    topK: 5,
    returnValues: false,
    returnMetadata: 'indexed',
    filter: { tenantId: { $eq: tenantId } },
  });
}
```

Index the filter field when inserting:

```typescript
await env.VECTORIZE_INDEX.insert([
  {
    id: crypto.randomUUID(),
    values: embedding,
    metadata: { tenantId, category },
    namespace: tenantId,   // namespace isolation also speeds graph walk
  },
]);
```

## 3. Parallelize Independent Queries with `Promise.all`

Multiple independent vector queries should never be serialised.

```typescript
async function multiQuerySearch(
  queries: number[][],
  env: Env,
): Promise<VectorizeMatches[][]> {
  const tasks = queries.map((vec) =>
    env.VECTORIZE_INDEX.query(vec, { topK: 5, returnValues: false }),
  );
  const settled = await Promise.all(tasks);
  return settled.map((r) => r.matches);
}
```

## 4. Cache Top-K Results in Workers KV for Repeat Queries

Semantic queries from users often cluster. Cache the embedding + result tuple in KV
with a short TTL.

```typescript
const CACHE_TTL = 30; // seconds – tune to staleness tolerance

async function cachedVectorQuery(
  embedding: number[],
  cacheKey: string,
  env: Env,
): Promise<VectorizeMatch[]> {
  const cached = await env.KV.get<VectorizeMatch[]>(cacheKey, 'json');
  if (cached) return cached;

  const result = await env.VECTORIZE_INDEX.query(embedding, {
    topK: 10,
    returnValues: false,
    returnMetadata: 'indexed',
  });

  await env.KV.put(cacheKey, JSON.stringify(result.matches), {
    expirationTtl: CACHE_TTL,
  });
  return result.matches;
}
```

## 5. Namespace Isolation for Hot vs. Cold Vectors

Put frequently-queried vectors in a dedicated namespace so the ANN index stays warm
and compactly traversable.

```typescript
// Insert into namespace based on recency / access tier
async function tieredInsert(
  id: string,
  embedding: number[],
  metadata: Record<string, string>,
  hot: boolean,
  env: Env,
) {
  await env.VECTORIZE_INDEX.insert([
    {
      id,
      values: embedding,
      metadata,
      namespace: hot ? 'hot' : 'archive',
    },
  ]);
}

// Query hot namespace first; fall back to archive only if needed
async function tieredQuery(embedding: number[], env: Env) {
  const hot = await env.VECTORIZE_INDEX.query(embedding, {
    topK: 10,
    returnValues: false,
    namespace: 'hot',
  });
  if (hot.matches.length >= 5) return hot.matches;

  const archive = await env.VECTORIZE_INDEX.query(embedding, {
    topK: 10,
    returnValues: false,
    namespace: 'archive',
  });
  return [...hot.matches, ...archive.matches]
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}
```

---

## Anti-patterns

- **`returnValues: true` by default** – doubles response payload for no benefit when you only
  need IDs and scores.
- **`topK: 100`** – large result sets require more graph traversal and more serialisation; use
  the smallest `topK` that satisfies UX.
- **No metadata index on filter fields** – without indexed metadata, Vectorize must post-filter
  after full ANN scan, eliminating the selectivity benefit.
- **Sequential fan-out** – awaiting each query in a loop instead of `Promise.all` adds full RTT
  per additional query.

## Gotchas

- `returnMetadata: 'all'` returns unindexed blob metadata too; `'indexed'` is faster and
  sufficient for most use cases.
- Namespace must be set at insert time; you cannot move a vector between namespaces without
  delete + re-insert.
- Vectorize is eventually consistent after `insert`/`upsert` – newly inserted vectors may not
  appear in query results for a few seconds.
- Filter fields must be scalar strings or numbers; nested objects in metadata are not filterable.

## Verification

```typescript
// Measure P50/P99 with Workers Analytics Engine
async function timedQuery(embedding: number[], env: Env) {
  const start = Date.now();
  const result = await env.VECTORIZE_INDEX.query(embedding, {
    topK: 10,
    returnValues: false,
  });
  const elapsed = Date.now() - start;
  env.AE.writeDataPoint({
    blobs: ['vectorize_query'],
    doubles: [elapsed, result.matches.length],
  });
  return result;
}
```

Run repeated queries and confirm P99 < 150 ms for warm namespaces with `topK ≤ 20`.

## Related

- `workers-kv-read-performance-mobile-cold-start.md`
- `workers-subrequest-fanout-parallelism.md`
- `d1-query-optimization.md`

## Sources

- https://developers.cloudflare.com/vectorize/reference/client-api/
- https://developers.cloudflare.com/vectorize/best-practices/
- https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
