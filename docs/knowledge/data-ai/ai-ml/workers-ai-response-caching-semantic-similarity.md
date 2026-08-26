# Workers AI Response Caching via Semantic Similarity

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Identical or near-identical user questions are each triggering a fresh inference call, burning token quota and adding 200–800 ms latency. AI Gateway's semantic cache works at the gateway layer with a coarse threshold; you need fine-grained control — custom similarity thresholds, per-user namespacing, and cache invalidation by topic — implemented directly in your Worker.

## Context

The pattern:
1. Embed the incoming query using Workers AI embeddings.
2. Compare the embedding against cached query embeddings stored in Vectorize.
3. If cosine similarity ≥ threshold, return the cached response from KV.
4. On a miss, run inference, then write the new (query-embedding, response) pair to Vectorize + KV.

This sidesteps AI Gateway's global cache and gives you per-tenant namespacing, TTL control, and threshold tuning at the application layer.

---

## 1. Embedding a Query and Checking Vectorize for a Match

```typescript
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  CACHE_INDEX: VectorizeIndex;   // Vectorize index storing query embeddings
  CACHE_RESPONSES: KVNamespace;  // KV storing cached response text keyed by vector ID
}

const EMBED_MODEL = "@cf/baai/bge-small-en-v1.5";
const SIMILARITY_THRESHOLD = 0.92; // tune per use-case
const CACHE_TTL_SECONDS = 3600;

async function getEmbedding(ai: Ai, text: string): Promise<number[]> {
  const result = await ai.run(EMBED_MODEL, { text });
  return result.data[0];
}

export async function semanticCacheLookup(
  env: Env,
  query: string,
): Promise<string | null> {
  const vector = await getEmbedding(env.AI, query);

  const matches = await env.CACHE_INDEX.query(vector, {
    topK: 1,
    returnMetadata: "none",
  });

  const top = matches.matches[0];
  if (!top || top.score < SIMILARITY_THRESHOLD) return null;

  return env.CACHE_RESPONSES.get(top.id);
}
```

## 2. Writing a New Entry to the Semantic Cache

```typescript
import { nanoid } from "nanoid"; // or use crypto.randomUUID()

export async function semanticCacheWrite(
  env: Env,
  query: string,
  response: string,
): Promise<void> {
  const vector = await getEmbedding(env.AI, query);
  const id = crypto.randomUUID();

  await Promise.all([
    env.CACHE_INDEX.upsert([{ id, values: vector }]),
    env.CACHE_RESPONSES.put(id, response, {
      expirationTtl: CACHE_TTL_SECONDS,
      metadata: { query: query.slice(0, 256), cachedAt: Date.now() },
    }),
  ]);
}
```

## 3. Full Worker Handler with Cache-Aside Logic

```typescript
const INFERENCE_MODEL = "@cf/meta/llama-3.1-8b-instruct";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { query } = await request.json<{ query: string }>();
    if (!query) return new Response("Missing query", { status: 400 });

    // 1. Check semantic cache
    const cached = await semanticCacheLookup(env, query);
    if (cached) {
      return Response.json({
        response: cached,
        source: "semantic-cache",
      });
    }

    // 2. Run inference on cache miss
    const result = await env.AI.run(INFERENCE_MODEL, {
      messages: [{ role: "user", content: query }],
      max_tokens: 512,
    });

    const responseText = result.response ?? "";

    // 3. Write to cache asynchronously (non-blocking)
    const ctx = (request as any)[Symbol.for("cloudflare:ctx")];
    if (ctx?.waitUntil) {
      ctx.waitUntil(semanticCacheWrite(env, query, responseText));
    } else {
      await semanticCacheWrite(env, query, responseText);
    }

    return Response.json({
      response: responseText,
      source: "inference",
    });
  },
};
```

## 4. Per-Tenant Namespace Partitioning

```typescript
// Each tenant gets its own Vectorize namespace to prevent cross-tenant cache hits

async function tenantCacheLookup(
  env: Env,
  tenantId: string,
  query: string,
): Promise<string | null> {
  const vector = await getEmbedding(env.AI, query);

  const matches = await env.CACHE_INDEX.query(vector, {
    topK: 1,
    filter: { tenantId: { $eq: tenantId } },
    returnMetadata: "none",
  });

  const top = matches.matches[0];
  if (!top || top.score < SIMILARITY_THRESHOLD) return null;

  return env.CACHE_RESPONSES.get(`${tenantId}:${top.id}`);
}

async function tenantCacheWrite(
  env: Env,
  tenantId: string,
  query: string,
  response: string,
): Promise<void> {
  const vector = await getEmbedding(env.AI, query);
  const id = crypto.randomUUID();

  await Promise.all([
    env.CACHE_INDEX.upsert([{
      id,
      values: vector,
      metadata: { tenantId },
    }]),
    env.CACHE_RESPONSES.put(`${tenantId}:${id}`, response, {
      expirationTtl: CACHE_TTL_SECONDS,
    }),
  ]);
}
```

## 5. Cache Invalidation by Topic Keyword

```typescript
// Invalidate all cached entries whose stored query contains a keyword
// by expiring the KV keys (Vectorize entries age out via scheduled cleanup)

export async function invalidateTopic(
  env: Env,
  tenantId: string,
  keyword: string,
): Promise<number> {
  let cursor: string | undefined;
  let invalidated = 0;

  do {
    const page = await env.CACHE_RESPONSES.list({
      prefix: `${tenantId}:`,
      cursor,
      limit: 100,
    });

    for (const key of page.keys) {
      const meta = key.metadata as { query?: string } | null;
      if (meta?.query?.toLowerCase().includes(keyword.toLowerCase())) {
        await env.CACHE_RESPONSES.delete(key.name);
        invalidated++;
      }
    }

    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  return invalidated;
}
```

---

## Anti-patterns

- **Using a threshold below 0.85** — scores below 0.85 allow semantically different questions (e.g., "What is RAM?" vs. "What is ROM?") to share a cached response. Start at 0.92 and tune down only with empirical data.
- **Embedding the full conversation history** — only embed the latest user turn for cache lookup; including history makes each lookup unique even for identical questions.
- **Blocking the response on cache writes** — always use `waitUntil` to write cache entries asynchronously; blocking adds 50–150 ms to every request.
- **Storing large responses directly in Vectorize metadata** — Vectorize metadata has a 1 KB per-record limit; always store response text in KV and only the ID in Vectorize.

## Gotchas

- Vectorize `query()` returns cosine similarity scores in the range [0, 1] for normalized embeddings; `bge-small-en-v1.5` returns L2-normalized vectors by default so cosine and dot-product scores are equivalent.
- KV TTL and Vectorize index entries have independent lifetimes. A KV expiry does not remove the Vectorize entry; stale vector IDs return KV misses rather than stale responses — this is safe but wastes index space.
- `filter` on Vectorize metadata requires the metadata field to be indexed at index creation time; add `--metadata-indexing-mode=all-indexes` or specific field indexing when creating the index.
- Workers AI embedding calls count against your Workers AI token quota even on cache hits when you embed the query for lookup.

## Verification

```bash
# First call — cache miss, inference runs
curl -X POST https://my-worker.workers.dev/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"What are Cloudflare Workers?"}'
# source: "inference"

# Second call with synonymous phrasing — should hit cache
curl -X POST https://my-worker.workers.dev/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Can you explain Cloudflare Workers to me?"}'
# source: "semantic-cache"  (if similarity >= 0.92)

# Inspect KV contents
wrangler kv key list --binding=CACHE_RESPONSES
```

## Related

- `semantic-caching-patterns.md`
- `ai-gateway-semantic-cache-threshold-tuning.md`
- `vectorize-cosine-similarity-threshold-tuning-workers.md`
- `workers-ai-batch-embedding-queues-pipeline.md`
- `workers-ai-prompt-template-kv-versioning.md`

## Sources

- Cloudflare Vectorize query API: https://developers.cloudflare.com/vectorize/reference/client-api/
- Workers AI BGE embedding model: https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/
- Cloudflare KV TTL and metadata: https://developers.cloudflare.com/kv/api/write-key-value-pairs/
