# Workers AI Inference Response Caching

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Paying Twice for the Same Answer

Generative AI inference is expensive. Every uncached call to Workers AI or an upstream model provider (via AI Gateway) burns GPU compute and adds 200–2000 ms of latency. Many production workloads repeatedly ask the same questions: product descriptions, FAQ answers, translation of static strings, structured data extraction from fixed schemas. Without caching, each request pays the full cost.

Workers AI does not cache inference results by default. AI Gateway adds optional semantic caching, but for deterministic or near-deterministic prompts a more controlled Cache API approach gives tighter TTL governance, exact cache-key semantics, and measurable cost attribution through Analytics Engine.

The goal is to intercept AI Gateway fetch calls inside a Worker, compute a stable cache key from the model identifier and prompt content, check the Cache API before forwarding the request upstream, and write the response into cache on a miss.

## Context

This pattern works for both Workers AI (via the AI binding) and AI Gateway proxied requests. The cache key design must handle the full prompt payload—system message, user message, model name, temperature, and any sampling parameters that affect output—since any difference in those fields can produce a different response. Deterministic outputs (temperature=0, top_p=1, seed fixed) can use long TTLs (hours to days). Generative outputs where slight variation is acceptable can use short TTLs (minutes) to amortize burst traffic.

Analytics Engine is used to record cache hits, misses, token costs (from the response's `usage` field), and latency. This data drives cost-savings dashboards and informs TTL tuning.

## Cache Key Design

```typescript
import { createHash } from 'node:crypto';

interface InferencePayload {
  model: string;
  messages: Array<{ role: string; content: string }>;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  seed?: number;
}

function buildCacheKey(payload: InferencePayload, cacheVersion = 'v1'): string {
  // Normalize: sort messages, strip whitespace, lowercase model
  const normalized = {
    v: cacheVersion,
    model: payload.model.toLowerCase(),
    messages: payload.messages.map(m => ({
      role: m.role,
      content: m.content.trim(),
    })),
    temperature: payload.temperature ?? 1.0,
    top_p: payload.top_p ?? 1.0,
    max_tokens: payload.max_tokens ?? null,
    seed: payload.seed ?? null,
  };
  const hash = createHash('sha256')
    .update(JSON.stringify(normalized))
    .digest('hex')
    .slice(0, 32);
  return `https://ai-cache.internal/${cacheVersion}/${hash}`;
}
```

The URL-shaped cache key is required because the Cache API indexes by Request URL. Include a `cacheVersion` token so you can bust the entire cache when the prompt template changes.

## Cache API Wrapping Pattern

```typescript
export interface Env {
  AI_GATEWAY_URL: string;
  AI_GATEWAY_TOKEN: string;
  ANALYTICS: AnalyticsEngineDataset;
}

const DETERMINISTIC_TTL = 60 * 60 * 6;  // 6 hours for temp=0
const GENERATIVE_TTL   = 60 * 5;        // 5 minutes for temp>0

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const payload: InferencePayload = await request.json();
    const isDeterministic = (payload.temperature ?? 1.0) === 0 && payload.seed != null;
    const ttl = isDeterministic ? DETERMINISTIC_TTL : GENERATIVE_TTL;
    const cacheKey = buildCacheKey(payload);
    const cacheRequest = new Request(cacheKey, { method: 'GET' });
    const cache = caches.default;

    const start = Date.now();
    const cached = await cache.match(cacheRequest);

    if (cached) {
      const body = await cached.json();
      ctx.waitUntil(recordMetric(env, 'hit', payload.model, 0, Date.now() - start));
      return Response.json({ ...body, _cache: 'HIT' });
    }

    // Cache miss — call AI Gateway
    const upstream = await fetch(env.AI_GATEWAY_URL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.AI_GATEWAY_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!upstream.ok) {
      return new Response(upstream.body, { status: upstream.status, headers: upstream.headers });
    }

    const data = await upstream.json<{ usage?: { total_tokens?: number } }>();
    const latencyMs = Date.now() - start;
    const tokens = data.usage?.total_tokens ?? 0;

    // Write to cache with TTL
    const cacheResponse = new Response(JSON.stringify(data), {
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': `public, max-age=${ttl}`,
      },
    });
    ctx.waitUntil(cache.put(cacheRequest, cacheResponse));
    ctx.waitUntil(recordMetric(env, 'miss', payload.model, tokens, latencyMs));

    return Response.json({ ...data, _cache: 'MISS' });
  },
};

async function recordMetric(
  env: Env,
  status: 'hit' | 'miss',
  model: string,
  tokens: number,
  latencyMs: number,
): Promise<void> {
  env.ANALYTICS.writeDataPoint({
    blobs: [status, model],
    doubles: [tokens, latencyMs],
    indexes: [model],
  });
}
```

## TTL Strategy and Cost Savings Measurement

For cost savings, query Analytics Engine for total tokens on misses vs total requests, then multiply by the model's per-token rate:

```typescript
// Query via Analytics Engine GraphQL (run from a scheduled Worker or external)
const query = `
  query CostSavings($accountId: String!, $since: String!) {
    viewer {
      accounts(filter: { accountTag: $accountId }) {
        aiCacheMetrics: workersAiCacheAdaptiveGroups(
          limit: 1000
          filter: { datetime_geq: $since }
          orderBy: [datetime_ASC]
        ) {
          sum { tokens: double2, requests: count }
          dimensions { status: blob1, model: blob2 }
        }
      }
    }
  }
`;

interface MetricRow {
  sum: { tokens: number; requests: number };
  dimensions: { status: string; model: string };
}

function computeSavings(rows: MetricRow[], pricePerThousandTokens: number): number {
  const misses = rows.filter(r => r.dimensions.status === 'miss');
  const hits   = rows.filter(r => r.dimensions.status === 'hit');
  const missTokens = misses.reduce((a, r) => a + r.sum.tokens, 0);
  const hitRequests = hits.reduce((a, r) => a + r.sum.requests, 0);
  // Assume average tokens per request from miss data
  const avgTokens = missTokens / (misses.reduce((a, r) => a + r.sum.requests, 0) || 1);
  const savedTokens = hitRequests * avgTokens;
  return (savedTokens / 1000) * pricePerThousandTokens;
}
```

Schedule this computation daily and surface it on your cost dashboard.

## Anti-patterns

- **Caching on the raw request body as a string** — HTTP body bytes can differ (field order, whitespace) for semantically identical payloads. Always normalize before hashing.
- **Using a single TTL for all models** — embeddings models are fully deterministic; chat completion models with temperature > 0 produce stochastic outputs. Use per-category TTLs.
- **Not versioning the cache key** — when you change the system prompt or model version, old cache entries become stale but still match. Bump `cacheVersion` on any prompt template change.
- **Caching streaming responses** — the Cache API cannot store `ReadableStream` responses. Consume the full body, cache it, then optionally re-stream to the client.

## Gotchas

- The Cache API in Workers is per-datacenter. A user in a different PoP will miss the cache on the first request. Tiered Cache (Smart Tiered Cache enabled) helps propagate popular entries, but inference caches are typically request-local hot-path caches, not edge-wide.
- `cache.put()` has a 512 MB response body limit, but AI responses are rarely larger than a few KB. Not an issue in practice.
- AI Gateway has its own semantic cache layer. Running both in parallel can cause double-caching. Disable AI Gateway's semantic cache if you manage cache keys yourself.
- `ctx.waitUntil()` extends the Worker lifetime for cache writes. Do not `await` the put inline if you want to return the response immediately.

## Verification

```bash
# Hit the Worker twice with the same payload and verify _cache field
PAYLOAD='{"model":"@cf/meta/llama-3-8b-instruct","messages":[{"role":"user","content":"What is 2+2?"}],"temperature":0,"seed":42}'

curl -s -X POST https://your-worker.example.com/ \
  -H 'Content-Type: application/json' \
  -d "$PAYLOAD" | jq '._cache'
# Expected first call: "MISS"

curl -s -X POST https://your-worker.example.com/ \
  -H 'Content-Type: application/json' \
  -d "$PAYLOAD" | jq '._cache'
# Expected second call (same PoP): "HIT"
```

Query Analytics Engine via Cloudflare GraphQL to confirm token counts are only recorded on misses.

## Related

- `workers-llm-streaming-responses.md`
- `api-response-caching.md`
- `analytics-engine-rum-web-vitals.md`
- `workers-cpu-time-optimization.md`

## Sources

- Cloudflare Cache API documentation: https://developers.cloudflare.com/workers/runtime-apis/cache/
- AI Gateway caching: https://developers.cloudflare.com/ai-gateway/configuration/caching/
- Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
