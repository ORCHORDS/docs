# Prompt Caching with KV: Reducing Workers AI Cost and Latency

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Repeated or near-identical LLM calls (FAQ bots, product description generation with the same system prompt, templated summarisation) waste AI neurons and add 200–800 ms round-trip latency per call. Hashing the system prompt + user message and caching the response in Workers KV with a TTL eliminates redundant model calls for identical inputs. Analytics Engine tracks cache hit rate and estimates cost savings.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Bindings: `AI`, `PROMPT_CACHE` (KV namespace), `ANALYTICS` (Analytics Engine dataset)
- Model: `@cf/meta/llama-3.1-8b-instruct`
- Cache key: SHA-256 of `model + systemPrompt + userMessage`
- TTL: configurable per call-site (default 3600 s)
- Tracking: cache hit/miss events written to Analytics Engine

---

## Section 1: Wrangler Configuration

```toml
# wrangler.toml
name = "cached-ai"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"

[[kv_namespaces]]
binding = "PROMPT_CACHE"
id = "<your-kv-namespace-id>"

[analytics_engine_datasets]
binding = "ANALYTICS"
dataset = "ai_cache_events"
```

## Section 2: Cache Key Generation

```typescript
// src/cache-key.ts
export async function buildCacheKey(
  model: string,
  systemPrompt: string,
  userMessage: string
): Promise<string> {
  const raw = `${model}\x00${systemPrompt}\x00${userMessage}`;
  const encoded = new TextEncoder().encode(raw);
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}
```

## Section 3: Cached AI Client

```typescript
// src/cached-ai.ts
import { Ai, KVNamespace, AnalyticsEngineDataset } from '@cloudflare/workers-types';
import { buildCacheKey } from './cache-key';

export interface CachedAiOptions {
  ai: Ai;
  cache: KVNamespace;
  analytics: AnalyticsEngineDataset;
  model: string;
  systemPrompt: string;
  userMessage: string;
  ttlSeconds?: number;
  temperature?: number;
  maxTokens?: number;
}

export interface CachedAiResult {
  response: string;
  cacheHit: boolean;
  cacheKey: string;
}

export async function runWithCache(opts: CachedAiOptions): Promise<CachedAiResult> {
  const {
    ai,
    cache,
    analytics,
    model,
    systemPrompt,
    userMessage,
    ttlSeconds = 3600,
    temperature = 0.7,
    maxTokens = 1024,
  } = opts;

  const cacheKey = await buildCacheKey(model, systemPrompt, userMessage);

  // Attempt cache read
  const cached = await cache.get(cacheKey);
  if (cached !== null) {
    // Record hit
    analytics.writeDataPoint({
      blobs: [model, 'hit'],
      doubles: [0],
      indexes: [cacheKey.slice(0, 16)],
    });
    return { response: cached, cacheHit: true, cacheKey };
  }

  // Cache miss — call the model
  const start = Date.now();
  const result = await (ai as any).run(model, {
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userMessage },
    ],
    max_tokens: maxTokens,
    temperature,
  });
  const latencyMs = Date.now() - start;
  const responseText = (result as { response?: string }).response ?? '';

  // Write to KV with TTL
  await cache.put(cacheKey, responseText, { expirationTtl: ttlSeconds });

  // Record miss + latency
  analytics.writeDataPoint({
    blobs: [model, 'miss'],
    doubles: [latencyMs],
    indexes: [cacheKey.slice(0, 16)],
  });

  return { response: responseText, cacheHit: false, cacheKey };
}
```

## Section 4: Worker Entry Point

```typescript
// src/index.ts
import { runWithCache } from './cached-ai';

export interface Env {
  AI: Ai;
  PROMPT_CACHE: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;
}

const SYSTEM_PROMPT =
  'You are a concise product description writer. ' +
  'Respond with a single paragraph of 2-3 sentences.';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('POST { "product": "..." }', { status: 405 });
    }

    const { product } = await request.json<{ product: string }>();
    if (!product?.trim()) return new Response('Missing product', { status: 400 });

    const { response, cacheHit, cacheKey } = await runWithCache({
      ai: env.AI,
      cache: env.PROMPT_CACHE,
      analytics: env.ANALYTICS,
      model: '@cf/meta/llama-3.1-8b-instruct',
      systemPrompt: SYSTEM_PROMPT,
      userMessage: `Write a product description for: ${product}`,
      ttlSeconds: 86_400, // 24 hours — product descriptions rarely change
    });

    return Response.json({
      description: response,
      cacheHit,
      cacheKey: cacheKey.slice(0, 8) + '…',
    });
  },
};
```

## Section 5: Cache Hit Rate Dashboard Query (Analytics Engine SQL API)

```bash
# Query via Analytics Engine SQL API (replace ACCOUNT_ID and API_TOKEN)
curl -s "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "query": "SELECT blob2 AS cache_result, COUNT() AS requests, AVG(double1) AS avg_latency_ms FROM ai_cache_events WHERE timestamp > NOW() - INTERVAL \'1\' DAY GROUP BY cache_result ORDER BY requests DESC"
  }' | jq '.data'
```

Expected output:
```json
[
  { "cache_result": "hit",  "requests": 820, "avg_latency_ms": 0 },
  { "cache_result": "miss", "requests": 180, "avg_latency_ms": 412 }
]
```

Cache hit rate: 82%. Estimated cost saving: 82% of AI neuron spend for this endpoint.

## Section 6: Cost Reduction Estimation

```typescript
// Rough formula — adjust neuron cost per your account tier
const NEURON_COST_USD_PER_1K = 0.0001; // example rate

function estimateSavings(hitCount: number, avgOutputTokens: number): number {
  // Each cache hit avoids ~avgOutputTokens neurons of generation
  const neuronsAvoided = hitCount * avgOutputTokens;
  return (neuronsAvoided / 1000) * NEURON_COST_USD_PER_1K;
}

// Example: 820 hits/day, 200 avg output tokens each
console.log(`Daily saving: $${estimateSavings(820, 200).toFixed(4)}`);
// → Daily saving: $0.0164
```

## Anti-patterns

- Do NOT cache responses for prompts containing real-time context (current time, live prices, per-user session data) — TTL cannot save you; the cache key will miss anyway but a bug could serve stale personalised content.
- Do NOT use the raw user input as the cache key string directly — hash it to avoid KV key length limits (512 bytes) and to normalise whitespace differences.
- Do NOT set `expirationTtl` to `0` — KV interprets this as "no expiry" not "immediate expiry"; use `delete()` for immediate invalidation.
- Do NOT block the `analytics.writeDataPoint()` call with `await` — it returns void and the write is asynchronous; awaiting it adds latency for no benefit.
- Do NOT store multi-megabyte responses in KV — KV values are capped at 25 MB, but latency degrades past ~1 MB; truncate or compress large responses.

## Gotchas

- KV reads have eventual consistency globally — a cache write in one region may not be visible in another for up to 60 seconds. For globally consistent caching at the cost of higher latency, use Durable Objects.
- `crypto.subtle.digest` is available in Workers without any import; no Node.js polyfill needed.
- Analytics Engine `writeDataPoint` silently drops events if the dataset is not provisioned in `wrangler.toml`.
- KV `expirationTtl` minimum is 60 seconds — values lower than 60 are rejected.
- The cache key covers the full system prompt; if you rotate the system prompt (e.g. for A/B testing) all existing cache entries are automatically invalidated by the hash mismatch.

## Verification

```bash
npx wrangler deploy

# First call — cache miss
curl -X POST https://cached-ai.<subdomain>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"product": "Sony WH-1000XM5 headphones"}'
# Response: { "cacheHit": false, ... }

# Second identical call — cache hit
curl -X POST https://cached-ai.<subdomain>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"product": "Sony WH-1000XM5 headphones"}'
# Response: { "cacheHit": true, ... }

# Inspect KV entries
npx wrangler kv key list --namespace-id=<your-kv-namespace-id>

# Force-invalidate a cached entry
npx wrangler kv key delete --namespace-id=<your-kv-namespace-id> <cache-key-hex>
```

## Related

- `documentation/docs/policies/ai-ml/workers-ai-json-mode-structured-output.md`
- `documentation/docs/policies/ai-ml/workers-ai-batch-inference-queues.md`
- `documentation/docs/policies/ai-ml/workers-ai-rag-reranking-vectorize.md`

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
