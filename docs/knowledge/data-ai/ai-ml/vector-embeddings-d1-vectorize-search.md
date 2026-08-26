# vector-embeddings-d1-vectorize-search

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project search returns poor results for semantically
similar queries ("loud concert" misses posts tagged
"noisy gig"). Pure D1 full-text search (FTS5) finds
keyword matches but ignores meaning. Adding Vectorize
for semantic search introduces a cold-start delay of
300-800 ms on the first query after a PoP warm-up,
making mobile search feel sluggish. Batching embeddings
for hundreds of new posts per minute exceeds the Workers
AI token budget.

## Context

example project posts are short (< 280 chars). The search UX
is a mobile text field that queries as the user types
(300 ms debounce). Hybrid search — Vectorize for semantic
recall + D1 FTS5 for keyword precision — improves result
quality. Embeddings are generated in a background Queue
consumer, not on the post-submit critical path.

## 1. Vectorize Namespace Setup

```toml
# wrangler.toml
[[vectorize]]
binding       = "VECTORIZE"
index_name    = "example project-posts"
dimensions    = 768
metric        = "cosine"
```

Use 768-d BAAI/bge embeddings (`@cf/baai/bge-base-en-v1.5`)
— smaller index, lower memory per query than 1536-d OpenAI
embeddings, and available inside Workers AI with no egress.

```
Model                          Dims  Latency  Notes
-----------------------------  ----  -------  -------------------
@cf/baai/bge-base-en-v1.5      768   80-150ms On-Workers-AI, free
@cf/baai/bge-small-en-v1.5     384   40-80ms  Lower recall
OpenAI text-embedding-3-large  3072  100-200ms Egress + cost
OpenAI text-embedding-3-small  1536  80-150ms  Egress + cost
```

BAAI bge-base-en-v1.5 at 768-d balances latency and recall
for short social-post content. Test against a example project eval
set before choosing.

## 2. Embedding Generation Pipeline (Queue Consumer)

Generate embeddings off the critical path:

```typescript
// Queue consumer (wrangler.toml: [[queues.consumers]])
export default {
  async queue(
    batch: MessageBatch<EmbedJob>,
    env: Env,
  ): Promise<void> {
    const BATCH_SIZE = 50;   // Workers AI embed batch limit

    for (let i = 0; i < batch.messages.length; i += BATCH_SIZE) {
      const slice = batch.messages.slice(i, i + BATCH_SIZE);
      const texts = slice.map(m => normalise(m.body.text));

      // Batch embed — single AI call for up to 50 texts
      const { data: embeddings } = await env.AI.run(
        "@cf/baai/bge-base-en-v1.5",
        { text: texts },
      );

      const vectors = slice.map((m, j) => ({
        id:       m.body.postId,
        values:   embeddings[j],
        metadata: {
          postId:    m.body.postId,
          createdAt: m.body.createdAt,
        },
      }));

      await env.VECTORIZE.upsert(vectors);
      slice.forEach(m => m.ack());
    }
  },
};
```

After upsert, mark the D1 row as embedding-ready:

```typescript
await env.DB.prepare(
  "UPDATE posts SET embedded=1 WHERE id IN (?)"
).bind(slice.map(m => m.body.postId).join(",")).run();
```

## 3. Hybrid Search: Vectorize + D1 FTS5

```sql
-- D1 FTS5 virtual table
CREATE VIRTUAL TABLE posts_fts USING fts5(
  id UNINDEXED,
  text,
  content='posts',
  content_rowid='rowid'
);
```

```typescript
async function hybridSearch(
  query: string,
  env: Env,
  limit = 20,
): Promise<Post[]> {
  // 1. Embed the query text
  const { data: [qVec] } = await env.AI.run(
    "@cf/baai/bge-base-en-v1.5",
    { text: [normalise(query)] },
  );

  // 2. Semantic neighbours from Vectorize
  const semantic = await env.VECTORIZE.query(qVec, {
    topK:             limit * 2,   // over-fetch for re-rank
    returnMetadata:   true,
  });

  const semanticIds = new Set(
    semantic.matches.map(m => m.id),
  );

  // 3. Keyword matches from D1 FTS5
  const keyword = await env.DB.prepare(
    "SELECT id FROM posts_fts WHERE text MATCH ? LIMIT ?"
  ).bind(query, limit * 2).all<{ id: string }>();

  const keywordIds = new Set(keyword.results.map(r => r.id));

  // 4. Merge: union, boost items in both sets
  const scored = new Map<string, number>();
  for (const m of semantic.matches) {
    scored.set(m.id, (scored.get(m.id) ?? 0) + m.score * 0.6);
  }
  for (const r of keyword.results) {
    scored.set(r.id, (scored.get(r.id) ?? 0) + 0.4);
  }

  const topIds = [...scored.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([id]) => id);

  // 5. Fetch full rows from D1
  if (topIds.length === 0) return [];
  const placeholders = topIds.map(() => "?").join(",");
  const rows = await env.DB.prepare(
    `SELECT * FROM posts WHERE id IN (${placeholders})` +
    " AND status='allow' ORDER BY created_at DESC"
  ).bind(...topIds).all<Post>();

  // Re-order by score
  const byId = new Map(rows.results.map(r => [r.id, r]));
  return topIds.map(id => byId.get(id)).filter(Boolean) as Post[];
}
```

## 4. Mobile Search UX: Debounce and Cold Start

Mobile keyboard input fires fast; debounce at 300 ms on
the client to avoid overwhelming the endpoint:

```typescript
// React / Next.js mobile client
const debouncedSearch = useMemo(
  () => debounce(async (q: string) => {
    if (q.length < 3) return;
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    setResults(await res.json());
  }, 300),
  [],
);
```

Vectorize cold-start latency (first query after PoP warm-up):

```
State                 Latency    Cause
--------------------  ---------  ---------------------------
Warm PoP              80-200 ms  Index resident in memory
Cold PoP (first hit)  300-800 ms Index loaded from storage
After 10 min idle     200-400 ms Partial eviction
```

Mitigate cold start: schedule a synthetic ping query via a
Cron Trigger every 5 min to keep the index warm at active
PoPs. Alternatively, pre-warm on Worker startup (once per
isolate lifecycle).

```typescript
// Lightweight keep-alive query in a scheduled event
async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
  await env.VECTORIZE.query(KEEPALIVE_VEC, { topK: 1 });
}
```

## 5. Batching and Token Budget

Workers AI embedding limits as of 2026-08:

```
Constraint              Limit     Notes
----------------------  --------  -------------------------
Max texts per batch     100       Per single AI.run call
Max chars per text      4096      Longer texts truncated
Requests/min (account)  50/model  Across all workers
Tokens/min              100k      Shared across all models
```

At 50 posts/batch and 80 tokens/post average, the burst
budget allows ~1250 posts/min before hitting the token
limit. Use the Queue dead-letter to catch failures and
retry with exponential back-off.

```typescript
// wrangler.toml queue consumer
[[queues.consumers]]
queue             = "example project-embed-queue"
max_batch_size    = 50
max_batch_timeout = 5       # seconds; balance latency vs batching
max_retries       = 3
dead_letter_queue = "example project-embed-dlq"
```

## Anti-patterns

- Generating embeddings synchronously on the post-submit path
  — adds 80-150 ms min to mobile submit latency; always queue.
- Using `topK = limit` in Vectorize then filtering in JS —
  post-filter can reduce results to zero; over-fetch by 2-3×.
- Querying Vectorize with unnormalised query text — trailing
  spaces and mixed case do not affect embedding quality, but
  stale FTS5 queries miss rows; normalise for FTS5 only.
- Storing the full embedding vector in D1 as a JSON blob —
  128 MB per Worker; 768-float arrays per row make D1 queries
  slow and blow the memory budget on large result sets.
- Omitting `returnMetadata: true` from the Vectorize query —
  the metadata contains `postId` needed to fetch from D1.

## Gotchas

- Vectorize `upsert` is eventually consistent; new posts may
  not appear in semantic search for 5-30 s after upsert.
- D1 FTS5 requires an explicit `INSERT INTO posts_fts`
  trigger or manual insert when a post is written; content
  tables do not auto-sync.
- `VECTORIZE.query` returns `score` as cosine similarity
  (0-1 for cosine metric); combine with FTS5 rank carefully
  — the scales are not directly comparable.
- Vectorize does not support filtering by metadata server-side
  in the current API; filter client-side in the Worker after
  the query, which reduces effective topK.
- Cold-start pings from Cron Triggers add ~1 req/5 min to the
  Workers AI request budget per active PoP.

## Verification

```bash
# 1. Semantic search returns results for paraphrase
curl "https://example project.example.com/api/search?q=loud+concert" \
  | jq '.[].text' | head -5

# 2. Confirm embeddings are being stored in Vectorize
wrangler vectorize get-vectors example project-posts \
  --ids "$(wrangler d1 execute example project_DB \
    --command 'SELECT id FROM posts LIMIT 1' --json \
    | jq -r '.[0].id')"

# 3. Measure P95 search latency from mobile (throttled)
# Use browser DevTools Network tab with "Slow 3G" preset
# Target: < 800 ms including debounce
```

## Related

- `cloudflare/vectorize-best-practices.md`
- `cloudflare/d1-full-text-search.md`
- `cloudflare/d1-read-replicas-mobile-api-latency.md`
- `ai-ml/embedding-models-vector-search-cloudflare.md`
- `ai-ml/rag-hybrid-search.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/vectorize/
- https://developers.cloudflare.com/vectorize/platform/limits/
- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/d1/sql-api/fts/
- https://developers.cloudflare.com/queues/
- https://blog.cloudflare.com/vectorize-vector-database-open-beta/
