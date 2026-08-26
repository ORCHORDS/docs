# Cloudflare AI Gateway — Request Caching and Cost Control

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project makes AI inference calls for content warnings, reply suggestions, and moderation labels. Many requests are semantically identical (the same trending post body generates the same content warning for thousands of viewers), yet the platform pays token costs on every call. Without a caching layer, a single viral post can trigger hundreds of redundant AI API calls within minutes. Cloudflare AI Gateway sits between the Worker and the AI provider, caching responses and tracking per-model costs.

## Context

Cloudflare AI Gateway is a reverse proxy for AI providers (Workers AI, OpenAI, Anthropic, etc.) that adds request logging, rate limiting, and caching without code changes to the inference call. The Worker routes all AI calls through the Gateway endpoint rather than calling the provider directly. Two cache modes are available: **exact-match cache** (identical prompt string → cached response) and **semantic cache** (similar prompt → cached response using embedding similarity). example project uses both: exact-match for deterministic feature prompts (e.g., classifying a specific post body), semantic cache for query-style prompts (e.g., FAQ lookups).

---

## 1. AI Gateway Setup

```bash
# Create a gateway via Cloudflare dashboard or API
# Dashboard: cloudflare.com → AI → AI Gateway → Create Gateway
# Name: example project-ai-gateway

# Gateway endpoint format:
# https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/{provider}/{model-path}
```

```toml
# wrangler.toml — pass gateway config as environment variable
[vars]
AI_GATEWAY_BASE = "https://gateway.ai.cloudflare.com/v1/abc123def456/example project-ai-gateway"
```

Workers AI calls through the gateway use the `gateway` option in `env.AI.run()`:

```typescript
// src/lib/ai-gateway.ts

interface GatewayOptions {
  cacheKey?: string;
  cacheTtl?: number;        // seconds
  skipCache?: boolean;
  metadata?: Record<string, string>;
}

export async function runWithGateway<T>(
  env: Env,
  model: string,
  inputs: Record<string, unknown>,
  options: GatewayOptions = {}
): Promise<T> {
  const result = await env.AI.run(model, inputs, {
    gateway: {
      id: 'example project-ai-gateway',
      // Exact-match cache TTL — default 0 (no cache)
      cache: options.skipCache ? false : {
        ttl: options.cacheTtl ?? 3600,    // 1-hour default
        ...(options.cacheKey ? { key: options.cacheKey } : {}),
      },
      // Metadata attached to the request in AI Gateway logs
      metadata: {
        feature: options.metadata?.feature ?? 'unknown',
        userId: options.metadata?.userId ?? 'anon',
        platform: options.metadata?.platform ?? 'web',
      },
    },
  });
  return result as T;
}
```

---

## 2. Exact-Match Cache Semantics

The exact-match cache keys on the **full serialized request body** (model + all inputs). A cache hit returns the stored response; token costs are zero for cached responses.

```
Exact-match cache behavior:
┌───────────────────────────────────────────────────────────────────┐
│  First request: POST /content-warning                             │
│  Body: {"messages":[{"role":"user","content":"Hot dog at beach"}]}│
│  → Cache MISS → Workers AI called → Response stored (TTL 3 600 s) │
│                                                                   │
│  Second request (same body within TTL):                           │
│  → Cache HIT → Response returned from cache, no AI call          │
│                                                                   │
│  Third request (body differs by one character):                   │
│  Body: {"messages":[{"role":"user","content":"hot dog at beach"}]}│
│  → Cache MISS (case-sensitive exact match)                        │
└───────────────────────────────────────────────────────────────────┘
```

**Key design rule**: normalize user input before forwarding to AI Gateway to maximize exact-match hit rate.

```typescript
// src/lib/normalize-prompt.ts
export function normalizeForCache(text: string): string {
  return text
    .trim()
    .toLowerCase()                      // Case-fold
    .replace(/\s+/g, ' ')              // Collapse whitespace
    .replace(/[^\w\s.,!?'-]/g, '')     // Strip unusual punctuation
    .slice(0, 500);                    // Cap length
}
```

Using a deterministic cache key overrides body-based keying — useful when you want to cache by post ID rather than post text:

```typescript
await runWithGateway(env, '@cf/meta/llama-3.1-8b-instruct', inputs, {
  cacheKey: `cw:${postId}`,    // post-scoped cache key
  cacheTtl: 86_400,            // 24 hours for content warnings on a fixed post
});
```

---

## 3. Semantic Cache

Semantic cache uses an embedding model to find cached responses for prompts that are semantically similar but textually different. This is particularly valuable for FAQ-style queries where users ask the same question with different wording.

```
Semantic cache: similarity threshold effect
┌──────────────────────┬────────────────────────────────────────────┐
│ Threshold            │ Behavior                                   │
├──────────────────────┼────────────────────────────────────────────┤
│ 0.95 (very strict)   │ Low hit rate; only near-identical queries  │
│ 0.85 (balanced)      │ Good hit rate; handles rephrasing well     │
│ 0.75 (loose)         │ High hit rate; may return off-topic answer │
│ < 0.75               │ Not recommended; accuracy degrades badly   │
└──────────────────────┴────────────────────────────────────────────┘
```

Configure semantic cache in the AI Gateway dashboard:
- Enable "Semantic Cache" per gateway
- Set similarity threshold (start at 0.85, tune based on hit rate vs accuracy)
- Semantic cache uses its own embedding model (Cloudflare manages this)

From the Worker, semantic cache is transparent — the same `gateway` option applies. The gateway decides whether to return a semantic hit. You can detect a cache hit via the response header:

```typescript
// Check if the AI Gateway served from cache (semantic or exact)
// AI Gateway adds: cf-aig-cache-status: HIT | MISS | BYPASS
export function wasCachedByGateway(response: Response): boolean {
  return response.headers.get('cf-aig-cache-status') === 'HIT';
}
```

Note: Workers AI binding responses via `env.AI.run()` with the `gateway` option do not expose raw HTTP headers. Use the AI Gateway analytics dashboard (or the Logpush integration) to observe cache hit rates rather than inspecting headers at runtime.

---

## 4. Per-Model Cost Tracking

AI Gateway logs every request with model, input tokens, output tokens, latency, and cache status. Export to analytics via Logpush for cost dashboards.

```
Workers AI pricing reference (mid-2026 — verify current at dash.cloudflare.com):
┌──────────────────────────────────────────┬───────────────────────────┐
│ Model                                    │ Neurons per run (approx.) │
├──────────────────────────────────────────┼───────────────────────────┤
│ @cf/meta/llama-3.1-8b-instruct           │ ~40 neurons / 1k tokens   │
│ @cf/meta/llama-3.2-1b-instruct           │ ~10 neurons / 1k tokens   │
│ @cf/microsoft/resnet-50 (image classify) │ ~1 neuron / image         │
│ @cf/baai/bge-base-en-v1.5 (embeddings)  │ ~1 neuron / 1k chars      │
│ @cf/llava-hf/llava-1.5-7b-hf (vision)   │ ~120 neurons / image      │
└──────────────────────────────────────────┴───────────────────────────┘
Cloudflare Workers AI free tier: 10,000 neurons/day on free plan.
Paid: included in Workers Paid plan; overage billed per neuron.
```

Track costs per feature using the metadata field:

```typescript
// Tag every AI call with its feature name for breakdown analytics
await runWithGateway(env, MODEL, inputs, {
  metadata: {
    feature: 'content_warning',
    userId: userId,
    platform: isMobile ? 'mobile' : 'desktop',
    communityId: communityId,
  },
});
```

Query cost breakdown from AI Gateway Logpush output (Cloudflare Analytics Engine):

```sql
-- Hypothetical Analytics Engine SQL (Workers Analytics Engine)
SELECT
  blob1 AS feature,
  blob3 AS platform,
  COUNT(*) AS requests,
  SUM(double2) AS total_tokens,
  COUNTIF(blob4 = 'HIT') AS cache_hits,
  ROUND(COUNTIF(blob4 = 'HIT') * 100.0 / COUNT(*), 1) AS hit_rate_pct
FROM ai_gateway_logs
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY feature, platform
ORDER BY total_tokens DESC;
```

---

## 5. Mobile vs. Desktop Request Patterns

Mobile clients generate different AI call patterns than desktop, affecting cache hit rates and cost:

```
Pattern comparison — example project mobile vs desktop:
┌─────────────────────────────┬──────────────────────┬──────────────────────┐
│ Factor                      │ Mobile               │ Desktop              │
├─────────────────────────────┼──────────────────────┼──────────────────────┤
│ Session AI calls/visit      │ 2-4 (feed scroll)    │ 8-15 (deeper browse) │
│ Typical prompt length       │ 80-120 chars         │ 200-400 chars        │
│ Likely cache hit rate       │ Higher (short posts) │ Lower (varied topics)│
│ Preferred TTL               │ 3 600 s (1 h)        │ 1 800 s (30 min)     │
│ Semantic cache benefit      │ High (same trending) │ Medium               │
│ max_tokens budget           │ 60-80 tokens         │ 100-200 tokens       │
└─────────────────────────────┴──────────────────────┴──────────────────────┘
```

Route mobile and desktop to different cache TTLs:

```typescript
export function getCacheTtl(feature: string, isMobile: boolean): number {
  const base: Record<string, number> = {
    content_warning:   86_400,  // Stable — post content doesn't change
    reply_suggestion:   1_800,  // Changes as thread evolves
    moderation_label:  86_400,  // Stable
    trending_summary:    3_600, // Refreshed hourly anyway
  };
  const ttl = base[feature] ?? 3_600;
  // Mobile gets longer TTL: repeated scroll sessions hit same posts
  return isMobile ? ttl * 2 : ttl;
}
```

---

## 6. Cache Invalidation

Content warnings cached for a post must be invalidated if a moderator edits the post or a community changes its content policy.

```typescript
// src/lib/cache-invalidate.ts
// AI Gateway provides a purge API for custom cache keys

export async function purgeGatewayCache(
  cacheKey: string,
  env: Env
): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai-gateway/gateways/example project-ai-gateway/cache`;

  const res = await fetch(url, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ keys: [cacheKey] }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Cache purge failed: ${res.status} ${body}`);
  }
}

// Called by moderator action Worker
async function onPostEdited(postId: string, env: Env): Promise<void> {
  await purgeGatewayCache(`cw:${postId}`, env);
  await purgeGatewayCache(`reply:${postId}`, env);
}
```

---

## Anti-Patterns

- **Bypassing the gateway for "fast paths"** — skipping the gateway for some calls breaks cost tracking and cache cohesion; always route through it.
- **Using `skipCache: true` by default** — defeats the entire caching benefit; only skip for genuinely non-cacheable calls (personalized real-time replies).
- **Not normalizing input before caching** — case differences, extra spaces, and punctuation variations each produce separate cache entries for identical semantic content.
- **Setting TTL to 0 on all content warning calls** — content warnings for fixed posts never change; caching at 24 h eliminates most cost on viral posts.
- **No metadata tags on calls** — without metadata, cost dashboards cannot break down spending by feature, making cost optimization impossible.
- **Infinite TTL for user-generated summaries** — summaries for evolving threads (comment threads, live discussions) become stale; use a short TTL (5–15 min) for dynamic content.

## Gotchas

- The `gateway` option in `env.AI.run()` is only available in the **Workers AI binding** — it does not apply to direct `fetch()` calls to OpenAI or Anthropic endpoints. For non-Workers-AI providers, proxy via the AI Gateway HTTP endpoint instead of using the binding.
- Semantic cache is **eventually consistent** — a new prompt may not benefit from semantic cache until the gateway has indexed it (typically within seconds, but no SLA).
- AI Gateway cache is **regional by default** — a cache hit in one Cloudflare region may miss in another. Check the dashboard setting for "Global Cache" if cross-region consistency is required.
- Cache purge via the API invalidates the **exact cache key** only; semantic cache neighbors of that key are not invalidated. If content policy changes require purging semantically similar entries, purge the category by TTL expiry rather than programmatic purge.
- The `cf-aig-cache-status` header is only observable when calling the gateway via HTTP, not via the `env.AI.run()` binding with `gateway` option. Use Logpush for observability.

## Verification

```bash
# 1. Confirm gateway is receiving requests
# Cloudflare Dashboard → AI → AI Gateway → example project-ai-gateway → Logs
# Look for requests with model = "@cf/meta/llama-3.1-8b-instruct"

# 2. Force a duplicate request and check cache hit in logs
BODY='{"text":"Photo of a sunset at the beach."}'
curl -X POST https://api.example.com/ai/content-warning \
  -H 'Content-Type: application/json' -d "$BODY"
# First call: logs show cache_status = MISS, tokens_used = N

curl -X POST https://api.example.com/ai/content-warning \
  -H 'Content-Type: application/json' -d "$BODY"
# Second call (within TTL): logs show cache_status = HIT, tokens_used = 0

# 3. Verify cost breakdown by feature (Cloudflare dashboard → AI Gateway → Analytics)
# Filter by: metadata.feature = "content_warning"
# Metric: total neurons consumed, cache hit rate %

# 4. Test cache invalidation
curl -X POST https://api.example.com/admin/cache/purge \
  -H 'Authorization: Bearer $ADMIN_TOKEN' \
  -d '{"cacheKey":"cw:post-abc123"}'
# Next content-warning call for that post: cache MISS (re-generates)
```

## Related

- `ai-gateway-caching.md` — general AI Gateway caching reference
- `ai-gateway-logging.md` — Logpush setup for AI Gateway events
- `ai-gateway-rate-limiting.md` — rate limiting per user via AI Gateway
- `cloudflare-ai-gateway-observability.md` — dashboards and alerting
- `ai-cost-monitoring.md` — cross-provider cost tracking
- `semantic-caching-patterns.md` — semantic cache design patterns

## Sources

- Cloudflare AI Gateway documentation: developers.cloudflare.com/ai-gateway
- Cloudflare Workers AI pricing: developers.cloudflare.com/workers-ai/pricing
- Cloudflare AI Gateway cache: developers.cloudflare.com/ai-gateway/configuration/caching
- Cloudflare Logpush: developers.cloudflare.com/logs/logpush
