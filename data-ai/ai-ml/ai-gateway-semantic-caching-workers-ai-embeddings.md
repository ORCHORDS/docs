# AI Gateway Semantic Caching with Workers AI Embeddings

date: 2026-08-24 / author: example.com / status: production

---

## Symptom / Use-case

AI Gateway's built-in semantic cache relies on Cloudflare's hosted similarity engine, which is a
black box with no tuneable similarity threshold per route. You want fine-grained control: embed
incoming prompts with Workers AI, query Vectorize for a cached response, return the hit if
cosine similarity exceeds a per-tenant threshold, and only forward cache misses to the upstream LLM
through AI Gateway. This pattern gives you transparent cache analytics, per-route thresholds, and
the ability to store rich metadata (model, token cost, latency) alongside cached responses.

## Context

AI Gateway sits between your Worker and the upstream LLM provider. In the custom-caching pattern,
you intercept the request *before* it reaches AI Gateway: embed the prompt with Workers AI
(`@cf/baai/bge-base-en-v1.5`), query Vectorize for the nearest neighbour, and on a cache hit
return the stored response directly — never touching AI Gateway or the upstream model. On a miss
you forward through AI Gateway, capture the response, embed the prompt, and upsert the
prompt-embedding + response into Vectorize for future hits.

Vectorize stores the prompt embedding (768 dims) and attaches the cached LLM response as metadata.
D1 stores full response payloads that exceed Vectorize's metadata size limit (~10 KB). A KV entry
keyed on the Vectorize vector ID bridges the two stores.

---

## Similarity threshold configuration

```typescript
// src/cache-config.ts

export interface CacheConfig {
  /** Cosine similarity required for a cache hit [0, 1]. Higher = more strict. */
  similarityThreshold: number;
  /** Max age of a cached entry in seconds before it is considered stale. */
  maxAgeSeconds: number;
  /** Vectorize namespace prefix for this route. */
  namespace: string;
}

export const ROUTE_CACHE_CONFIGS: Record<string, CacheConfig> = {
  "/api/chat": {
    similarityThreshold: 0.92,
    maxAgeSeconds: 3600,
    namespace: "chat",
  },
  "/api/summarize": {
    similarityThreshold: 0.97, // summaries are more sensitive to prompt variation
    maxAgeSeconds: 86400,
    namespace: "summarize",
  },
  "/api/classify": {
    similarityThreshold: 0.99, // classification prompts must be near-identical
    maxAgeSeconds: 43200,
    namespace: "classify",
  },
};

export function getConfig(pathname: string): CacheConfig {
  return (
    ROUTE_CACHE_CONFIGS[pathname] ?? {
      similarityThreshold: 0.95,
      maxAgeSeconds: 3600,
      namespace: "default",
    }
  );
}
```

---

## Embedding and cache lookup

```typescript
// src/semantic-cache.ts
import { getConfig } from "./cache-config";

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  RESPONSE_CACHE: KVNamespace;
}

const EMBED_MODEL = "@cf/baai/bge-base-en-v1.5";

export interface CacheLookupResult {
  hit: boolean;
  response?: string;
  score?: number;
  vectorId?: string;
}

async function embedPrompt(ai: Ai, prompt: string): Promise<number[]> {
  const result = await ai.run(EMBED_MODEL as any, { text: [prompt] });
  const vec: number[] = (result as any).data?.[0] ?? [];
  if (vec.length === 0) throw new Error("Empty embedding");
  return vec;
}

export async function lookupCache(
  env: Env,
  pathname: string,
  prompt: string,
): Promise<CacheLookupResult> {
  const config = getConfig(pathname);
  const queryVec = await embedPrompt(env.AI, prompt);

  const matches = await env.VECTORIZE.query(queryVec, {
    topK: 1,
    filter: { namespace: config.namespace },
    returnMetadata: "none",
  });

  const top = matches.matches[0];
  if (!top || top.score < config.similarityThreshold) {
    return { hit: false };
  }

  // Retrieve response payload from KV (faster + no metadata size limit)
  const stored = await env.RESPONSE_CACHE.get(`resp:${top.id}`);
  if (!stored) {
    // KV and Vectorize out of sync — treat as miss
    return { hit: false };
  }

  const parsed = JSON.parse(stored) as { response: string; timestamp: number };
  const ageSeconds = (Date.now() - parsed.timestamp) / 1000;

  if (ageSeconds > config.maxAgeSeconds) {
    // Stale entry — evict asynchronously and return miss
    Promise.all([
      env.VECTORIZE.deleteByIds([top.id]),
      env.RESPONSE_CACHE.delete(`resp:${top.id}`),
    ]).catch(console.error);
    return { hit: false };
  }

  return { hit: true, response: parsed.response, score: top.score, vectorId: top.id };
}
```

---

## Cache population after an AI Gateway upstream call

```typescript
// src/cache-write.ts
import type { Env } from "./semantic-cache";
import { getConfig } from "./cache-config";

const EMBED_MODEL = "@cf/baai/bge-base-en-v1.5";

/** Called after a successful upstream response to populate the cache. */
export async function populateCache(
  env: Env,
  pathname: string,
  prompt: string,
  response: string,
): Promise<void> {
  const config = getConfig(pathname);

  // Embed the prompt
  const result = await env.AI.run(EMBED_MODEL as any, { text: [prompt] });
  const vec: number[] = (result as any).data?.[0] ?? [];
  if (vec.length === 0) return;

  const vectorId = crypto.randomUUID();
  const payload = JSON.stringify({ response, timestamp: Date.now() });

  // Upsert into Vectorize with namespace metadata for filtering
  await env.VECTORIZE.upsert([
    {
      id: vectorId,
      values: vec,
      metadata: { namespace: config.namespace },
    },
  ]);

  // Store response in KV — TTL slightly longer than cache maxAge so KV doesn't
  // expire before Vectorize can return a hit (Vectorize has no TTL mechanism)
  await env.RESPONSE_CACHE.put(`resp:${vectorId}`, payload, {
    expirationTtl: config.maxAgeSeconds + 300,
  });
}
```

---

## Worker entry point integrating AI Gateway

```typescript
// src/index.ts
import { lookupCache, type Env as CacheEnv } from "./semantic-cache";
import { populateCache } from "./cache-write";

export interface Env extends CacheEnv {
  AI_GATEWAY_URL: string; // e.g. https://gateway.ai.cloudflare.com/v1/{account}/{gateway}/
  UPSTREAM_API_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const url = new URL(request.url);
    const bodyText = await request.text();
    let body: { messages?: Array<{ role: string; content: string }> };
    try {
      body = JSON.parse(bodyText);
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    // Extract the user prompt for embedding
    const lastUser = [...(body.messages ?? [])].reverse().find((m) => m.role === "user");
    const prompt = lastUser?.content ?? bodyText;

    // 1. Semantic cache lookup
    const cacheResult = await lookupCache(env, url.pathname, prompt);
    if (cacheResult.hit) {
      return new Response(
        JSON.stringify({ choices: [{ message: { role: "assistant", content: cacheResult.response } }] }),
        {
          headers: {
            "Content-Type": "application/json",
            "X-Cache": "HIT",
            "X-Cache-Score": String(cacheResult.score?.toFixed(4)),
          },
        },
      );
    }

    // 2. Forward to upstream through AI Gateway
    const upstreamUrl = `${env.AI_GATEWAY_URL}openai/chat/completions`;
    const upstreamResp = await fetch(upstreamUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${env.UPSTREAM_API_KEY}`,
      },
      body: bodyText,
    });

    if (!upstreamResp.ok) {
      return new Response(await upstreamResp.text(), { status: upstreamResp.status });
    }

    const upstreamBody = await upstreamResp.json() as any;
    const assistantContent: string =
      upstreamBody?.choices?.[0]?.message?.content ?? "";

    // 3. Populate cache asynchronously — don't block the response
    if (assistantContent) {
      populateCache(env, url.pathname, prompt, assistantContent).catch(console.error);
    }

    return new Response(JSON.stringify(upstreamBody), {
      headers: {
        "Content-Type": "application/json",
        "X-Cache": "MISS",
      },
    });
  },
};
```

---

## Cache hit-rate analytics with Analytics Engine

```typescript
// src/analytics.ts
export interface Env {
  CACHE_AE: AnalyticsEngineDataset;
}

export function recordCacheEvent(
  ae: AnalyticsEngineDataset,
  pathname: string,
  hit: boolean,
  score: number | undefined,
  durationMs: number,
): void {
  ae.writeDataPoint({
    blobs: [pathname, hit ? "HIT" : "MISS"],
    doubles: [hit ? 1 : 0, score ?? 0, durationMs],
    indexes: [pathname],
  });
}

// Query example (Analytics Engine SQL API):
// SELECT
//   blob2 AS cache_result,
//   countIf(double1 = 1) AS hits,
//   count() AS total,
//   avg(double2) AS avg_score,
//   avg(double3) AS avg_duration_ms
// FROM CACHE_AE
// WHERE timestamp > NOW() - INTERVAL '1' HOUR
// GROUP BY cache_result
```

## Anti-patterns

- **Embedding the full messages array as cache key** — system prompts, conversation history, and
  user messages all mixed together produces embeddings that match poorly; embed only the semantic
  core (the latest user turn).
- **Using a single global similarity threshold** — high-variance tasks (creative writing, code
  generation) need high thresholds (≥ 0.97); factual Q&A tolerates lower (0.90). Calibrate per
  route.
- **Storing large responses in Vectorize metadata** — Vectorize metadata has a ~10 KB limit; store
  payloads in KV or R2 and keep only the reference ID in metadata.
- **Not evicting stale entries** — Vectorize has no native TTL; track timestamps in KV and evict
  on stale hits or via a nightly Cron Trigger.
- **Blocking the response on cache write** — embedding and upserting the response vector adds
  50-100 ms; always fire-and-forget the write path.

## Gotchas

- Vectorize `query` returns up to `topK` results; with `topK: 1` and a namespace filter you still
  scan the full index — use namespace metadata filters to scope the search.
- The BGE-base model produces 768-dimensional vectors; ensure your Vectorize index was created with
  `dimensions: 768` and `metric: cosine`.
- Workers AI embedding calls count toward your AI billing even for cache population; at high cache-hit
  rates the embed cost is negligible, but at low hit rates you pay embed + upstream costs.
- AI Gateway's own semantic cache and this pattern are mutually exclusive for the same route —
  disable AI Gateway caching if implementing custom semantic cache to avoid double-caching.

## Verification

```bash
# First call — expect MISS
curl -sX POST https://your-worker.workers.dev/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What is the capital of France?"}]}' \
  -D - | grep X-Cache

# Semantically equivalent second call — expect HIT
curl -sX POST https://your-worker.workers.dev/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Capital city of France?"}]}' \
  -D - | grep -E "X-Cache|X-Cache-Score"
```

## Related

- `ai-gateway-caching.md` — AI Gateway native cache configuration
- `ai-gateway-semantic-cache-threshold-tuning.md` — threshold calibration methodology
- `ai-gateway-semantic-cache-hit-rate-analytics-engine.md` — measuring hit rate
- `vectorize-cosine-similarity-threshold-tuning-workers.md` — Vectorize query tuning
- `workers-ai-embedding-cache-kv-ttl.md` — caching embeddings to avoid recomputation
- `semantic-caching-patterns.md` — general semantic caching patterns

## Sources

- AI Gateway documentation: https://developers.cloudflare.com/ai-gateway/
- Vectorize query API: https://developers.cloudflare.com/vectorize/reference/client-api/
- Workers AI text embeddings: https://developers.cloudflare.com/workers-ai/models/#text-embeddings
