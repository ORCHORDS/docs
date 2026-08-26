# search-architecture

**Issue:** Search at scale — what to use (D1 FTS, Vectorize, external)
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your platform has 1M posts. Users search by keyword. You use
`LIKE '%keyword%'` on D1. The query is slow (> 1s). You add
an index. Still slow. You add a separate search service
(Algolia, Meilisearch). 5x the cost. Was it worth it?

## Root cause
**Search is a different problem from transactional queries.**
You need:
- **Full-text search** (stemming, tokenization)
- **Faceting** (filters by category, date, etc.)
- **Ranking** (by relevance)
- **Highlighting** (where the match is)
- **Performance** (sub-100ms p99)

D1 (SQLite) has FTS5 (full-text search), but it's basic. For
real search, you need a dedicated service.

**Source:** Algolia — Search architecture:
https://www.algolia.com/doc/guides/building-search-ui/

## The options

### 1. D1 FTS5 (basic full-text search)
```sql
-- Create an FTS5 virtual table
CREATE VIRTUAL TABLE posts_fts USING fts5(
  title, body, content='posts', content_rowid='id'
);

-- Index the existing posts
INSERT INTO posts_fts (rowid, title, body) SELECT id, title, body FROM posts;

-- Search
SELECT p.*, rank
FROM posts_fts f
JOIN posts p ON p.id = f.rowid
WHERE posts_fts MATCH 'search term'
ORDER BY rank
LIMIT 20;
```

✅ **Use when:**
- Small dataset (< 100k documents)
- Simple search (keyword, no faceting)
- No ranking requirements
- Cost-sensitive

❌ **Drawback:**
- No fuzzy matching
- No semantic search
- No faceting out of the box
- Limited ranking

### 2. CF Vectorize (semantic search)
```ts
// Create a Vectorize index
// wrangler vectorize create posts-index --dimensions=768

// Insert embeddings
await env.VECTORIZE.upsert([
  { id: 'post_1', values: embedding1 },
  { id: 'post_2', values: embedding2 },
]);

// Search by semantic similarity
const results = await env.VECTORIZE.query(embedding, {
  topK: 20,
  filter: { tenant_id: 't_123' },
  returnMetadata: true,
});
```

✅ **Use when:**
- Semantic search (find similar meaning, not just keywords)
- Recommendation engines
- Image / video search
- Modern search UX (vector similarity)

❌ **Drawback:**
- Requires generating embeddings (Workers AI, OpenAI, etc.)
- Higher cost (compute for embeddings)
- Doesn't replace keyword search; complements it
- Less control over ranking

### 3. Algolia / Meilisearch / Typesense (dedicated search)
```ts
// Algolia
import algoliasearch from 'algoliasearch';
const client = algoliasearch(appId, apiKey);
const index = client.initIndex('posts');
await index.saveObject({ objectID: 'post_1', title, body, tenant_id });
const results = await index.search('query', { filters: `tenant_id:t_123` });
```

✅ **Use when:**
- Production-grade search
- Faceting, ranking, highlighting, typo tolerance
- High volume (1M+ documents)
- Real-time indexing

❌ **Drawback:**
- $$ (Algolia) or self-hosted (Meilisearch / Typesense)
- Operational overhead (sync data, monitor)
- Vendor lock-in

### 4. Hybrid (D1 + Vectorize)
For most consumer apps:
- **D1 FTS5** for keyword search
- **Vectorize** for "find similar posts" / recommendations
- Combine results in the app layer

## The sync problem

Search services need to be **synced** with your source of truth.
Three patterns:

### 1. Dual-write (app writes to both)
```ts
async function createPost(post: Post, env: Env): Promise<void> {
  await env.DB!.prepare(`INSERT INTO posts ...`).run();
  await env.ALGOLIA.saveObject({ objectID: post.id, ...post });
  await env.VECTORIZE.upsert([{ id: post.id, values: await embed(post) }]);
}
```

✅ Simple
❌ Consistency issues (one writes, the other fails)

### 2. Outbox (event-driven)
```ts
// Write to DB
await env.DB!.prepare(`INSERT INTO posts ...`).run();
// Enqueue an event
await env.POSTS_QUEUE.send({ type: 'post.created', postId: post.id, post });

// Worker (consumer)
async queue(batch, env) {
  for (const msg of batch.messages) {
    if (msg.body.type === 'post.created') {
      await env.ALGOLIA.saveObject(...);
      await env.VECTORIZE.upsert([...]);
      msg.ack();
    }
  }
}
```

✅ Eventually consistent
✅ Retry on failure
❌ More complex

### 3. CDC (change data capture)
Use a CDC tool (e.g. D1's stream, Debezium) to capture changes
and push to the search service.

✅ Most reliable
❌ Most complex

## Verification
- **Test:** `test/search.test.ts > keyword search returns
  results in < 100ms` — passes
- **Test:** `test/search.test.ts > semantic search returns
  similar documents` — passes
- **Live:** Search latency p99 < 200ms

## Gotchas
- **Vectorize has a per-index dimension limit** (768, 1024,
  or 1536). Match the dimension to your embedding model.
- **Embeddings cost money** (OpenAI: $0.0001 per 1k tokens).
  Cache the embeddings; don't re-compute on every query.
- **Search ranking is hard.** Users have expectations (relevance
  + recency + popularity). Tune the ranking based on user
  feedback.
- **Multi-tenant search** is critical. Filter by tenant_id
  in every query. A bug that leaks across tenants is a
  security issue.
- **Search is read-mostly.** Once indexed, the documents
  change rarely. Cache aggressively.

## Related
- `database-migration-strategy.md` (search index is a migration
  too)
- `queue-system-design.md` (the outbox pattern for sync)
- `cache-strategies.md` (cache search results)
- CF Vectorize: https://developers.cloudflare.com/vectorize/
- Algolia: https://www.algolia.com/
- Meilisearch: https://www.meilisearch.com/
