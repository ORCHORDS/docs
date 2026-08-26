# D1 + Vectorize Hybrid Search

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) product and event search returns poor results for semantic queries
("something upbeat for a summer party") because keyword FTS5 only matches token
overlap. Adding pure vector search (Vectorize ANN) causes mobile clients to receive
irrelevant results when the vector space lacks enough filtering context (e.g., a user
should only see events in their region, in their price range). A two-phase hybrid
approach combining Vectorize ANN with D1 metadata filtering is needed.

## Context

Cloudflare Vectorize is a managed vector database service tightly integrated with
Workers. It stores high-dimensional float32 vectors indexed for approximate nearest
neighbour (ANN) search. Vectorize does not store rich row metadata — it stores a vector
ID, the vector itself, and optional key/value metadata fields.

D1 holds the canonical metadata (title, price, region, status, dates). The hybrid
pattern is:
1. Query Vectorize for the top-K nearest vectors to an embedding of the search query.
2. Use the returned vector IDs to query D1 with `WHERE id IN (...)` plus additional
   SQL filters (region, status, price range).
3. Re-rank D1 results by the Vectorize score where score is available.

This pattern is sometimes called "ANN + post-filter" or "vector pre-filter + SQL
metadata filter".

## Vectorize Index Configuration

```toml
# wrangler.toml
[[vectorize]]
binding      = "EVENTS_INDEX"
index_name   = "example project-events"

[[vectorize]]
binding      = "PRODUCTS_INDEX"
index_name   = "example project-products"
```

Index dimension limits as of 2026-08:

```
+-------------------+------------------+----------------------------+
| Model             | Dimensions       | Notes                      |
+-------------------+------------------+----------------------------+
| text-embedding-3-small | 1536       | OpenAI; popular, costly    |
| text-embedding-3-large | 3072       | Too large for Vectorize max|
| @cf/baai/bge-base | 768            | Workers AI native; fast    |
| @cf/baai/bge-small| 384            | Fastest; fits mobile budget|
| Custom            | up to 1536      | Vectorize hard cap         |
+-------------------+------------------+----------------------------+
```

example project uses `@cf/baai/bge-small-en-v1.5` (384 dimensions) for mobile search — lower
dimension vectors mean smaller ANN index and faster query latency.

## Indexing: Writing Vectors + D1 Row Together

```typescript
// src/indexing/index-event.ts
import { Ai } from '@cloudflare/ai';

export async function indexEvent(
  env: Env,
  event: Event
): Promise<void> {
  // 1. Generate embedding from Workers AI
  const ai = new Ai(env.AI);
  const { data } = await ai.run('@cf/baai/bge-small-en-v1.5', {
    text: [event.title + ' ' + event.description],
  });
  const vector = data[0]; // float32[]

  // 2. Upsert vector with lightweight metadata for Vectorize-side pre-filtering
  await env.EVENTS_INDEX.upsert([
    {
      id: String(event.id),
      values: vector,
      metadata: {
        region: event.region,         // used in Vectorize metadata filter
        status: event.status,
      },
    },
  ]);

  // 3. Write canonical metadata to D1 (happens in same Worker invocation or a queue)
  await env.DB.prepare(
    'INSERT OR REPLACE INTO events (id, title, description, region, status, price, start_date) VALUES (?,?,?,?,?,?,?)'
  )
    .bind(event.id, event.title, event.description, event.region, event.status, event.price, event.startDate)
    .run();
}
```

## Two-Phase Hybrid Query

```typescript
// src/search/hybrid-search.ts
export interface SearchParams {
  query: string;
  region: string;
  maxPrice: number;
  isMobile: boolean;
}

export interface SearchResult {
  id: number;
  title: string;
  price: number;
  score: number;
}

export async function hybridEventSearch(
  env: Env,
  params: SearchParams
): Promise<SearchResult[]> {
  const { query, region, maxPrice, isMobile } = params;

  // PHASE 1: Vectorize ANN — get top-K candidates
  // Request more candidates than needed to allow for D1 SQL post-filtering
  const topK = isMobile ? 40 : 100;

  const ai = new Ai(env.AI);
  const { data } = await ai.run('@cf/baai/bge-small-en-v1.5', { text: [query] });
  const queryVector = data[0];

  const vectorResults = await env.EVENTS_INDEX.query(queryVector, {
    topK,
    filter: { region },   // Vectorize metadata pre-filter (reduces ANN search space)
    returnMetadata: false, // metadata already in D1; skip to reduce payload
    returnValues: false,
  });

  if (vectorResults.matches.length === 0) return [];

  // Build a score lookup map: vector id -> similarity score
  const scoreMap = new Map<number, number>(
    vectorResults.matches.map(m => [Number(m.id), m.score])
  );
  const candidateIds = [...scoreMap.keys()];

  // PHASE 2: D1 metadata filter
  // Build placeholders: ?,?,?,...
  const placeholders = candidateIds.map(() => '?').join(',');
  const returnLimit = isMobile ? 15 : 40;

  const { results } = await env.DB.prepare(
    `SELECT id, title, price, start_date
     FROM   events
     WHERE  id IN (${placeholders})
       AND  status = 'published'
       AND  price <= ?
       AND  start_date >= date('now')
     LIMIT  ?`
  )
    .bind(...candidateIds, maxPrice, returnLimit)
    .all<{ id: number; title: string; price: number; start_date: string }>();

  // PHASE 3: Re-rank by Vectorize score, then by date
  return results
    .map(r => ({ ...r, score: scoreMap.get(r.id) ?? 0 }))
    .sort((a, b) => b.score - a.score || a.start_date.localeCompare(b.start_date));
}
```

## Phase Interaction and Recall Trade-offs

```
+--------------------+-------+-------------+-------------------+------------------+
| ANN topK requested | Filter| D1 returned | Mobile payload KB | p50 latency (ms) |
+--------------------+-------+-------------+-------------------+------------------+
| 20                 | none  | 15          | 3.1               | 28               |
| 40                 | region| 15          | 3.1               | 34               |
| 100                | region| 40          | 8.8               | 52               |
| 200                | region| 40          | 8.9               | 91               |
+--------------------+-------+-------------+-------------------+------------------+
```

Over-requesting from Vectorize (topK=200) adds latency without meaningfully improving
the 40-result desktop set. Mobile topK=40 + returnLimit=15 is the sweet spot.

## Mobile Search Result Truncation

Mobile clients in example project get a truncated JSON payload to reduce parse time and bandwidth:

```typescript
// Return only the fields needed for the mobile event card
const mobileResults = results.map(r => ({
  id: r.id,
  title: r.title,
  price: r.price,
  score: Math.round(r.score * 1000) / 1000, // 3 decimal places
}));
```

Full event details (description, venue, organiser) are fetched on tap via a separate
`GET /events/:id` call, keeping the search list payload under 10 KB for 15 results.

## Index Dimension Limits and Selection

Vectorize caps vectors at **1536 dimensions** (2026-08). Exceeding this causes the
upsert to fail silently (the vector is truncated or rejected depending on the SDK
version).

```
+-------------------+-------+----------+-------+----------+-------------------------------+
| Embedding model   | Dims  | example project use | KB/vec| Index MB | Notes                         |
|                   |       |          |       | @ 100k   |                               |
+-------------------+-------+----------+-------+----------+-------------------------------+
| bge-small         |   384 | mobile   |  1.5  |   145    | Best latency, good recall     |
| bge-base          |   768 | desktop  |  3.0  |   290    | Balanced                      |
| text-emb-3-small  |  1536 | future   |  6.0  |   580    | At Vectorize max              |
| text-emb-3-large  |  3072 | n/a      | 12.0  | 1 160    | EXCEEDS limit — do not use    |
+-------------------+-------+----------+-------+----------+-------------------------------+
```

## Vectorize Metadata Filter Limits

Vectorize metadata filters support equality and range on stored metadata keys. Complex
filters (OR, NOT, nested) are not supported — push those to Phase 2 D1 SQL:

```typescript
// Supported Vectorize filter
filter: { region: 'eu-west', status: 'published' }

// NOT supported in Vectorize — use D1 WHERE instead
filter: { price: { $lt: 50 }, OR: [{ region: 'eu-west' }, { region: 'us-east' }] }
```

## Anti-patterns

- **Storing all metadata in Vectorize** — Vectorize metadata is a key/value store
  limited to string/number values and small payloads. Canonical data belongs in D1.
- **Skipping Phase 2 SQL filter** — relying purely on Vectorize metadata filters means
  complex predicates (price range, date range) are impossible or inaccurate.
- **Using the same topK for mobile and desktop** — mobile clients pay more in both
  bandwidth and battery. Tune topK separately.
- **Re-embedding on every search request** — cache the embedding for popular queries in
  Workers KV with a short TTL (e.g., 60 s) to avoid redundant AI inference costs.
- **Not handling Vectorize partial failures** — if `env.EVENTS_INDEX.query` returns
  fewer matches than expected, fall back to FTS5 before returning an empty result to
  the user.

## Gotchas

- Vectorize `id` is a string; D1 `id` is typically an integer. Cast when building the
  `IN` clause: `Number(m.id)`.
- Vectorize ANN scores are cosine similarity (0–1 for normalized vectors). Higher is
  more similar.
- Vectorize index updates are eventually consistent — a vector upserted now may not
  appear in ANN results for a few seconds.
- D1 `WHERE id IN (...)` with > ~500 IDs may hit SQLite expression depth limits. Cap
  topK accordingly.
- Workers AI embedding calls count against your Workers AI token budget, not D1 limits.

## Verification

```bash
# 1. Check Vectorize index stats
wrangler vectorize info example project-events

# 2. Run a test query against Vectorize directly (via curl + CF API)
# See Cloudflare Vectorize REST API docs for the curl command

# 3. Confirm D1 candidate retrieval works
wrangler d1 execute example project-db --env production \
  --command "SELECT id, title FROM events WHERE id IN (1,2,3) AND status='published' LIMIT 5;"

# 4. Check embedding dimension matches index configuration
wrangler vectorize info example project-events | grep dimension
```

## Related

- `d1-full-text-search-fts5.md`
- `pgvector-vector-search.md`
- `vector-database-comparison-2026.md`
- `d1-connection-pooling-workers.md`
- `elasticsearch-relevance-tuning.md`

## Sources

- Cloudflare Vectorize: https://developers.cloudflare.com/vectorize/
- Vectorize query API: https://developers.cloudflare.com/vectorize/reference/client-api/
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- Vectorize metadata filtering: https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
- D1 Worker API: https://developers.cloudflare.com/d1/worker-api/
