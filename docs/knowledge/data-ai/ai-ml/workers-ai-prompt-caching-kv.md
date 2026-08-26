# Workers AI Prompt Response Caching with KV

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers AI inference costs money and burns CPU time. Many requests are semantically identical (same FAQ question, same system prompt + slightly rephrased query that hashes identically). A KV-backed cache-aside layer in front of the model cuts repeated inference cost to near zero and slashes p99 latency from ~2 s to ~10 ms for cache hits. This article covers cache-key generation, TTL strategy by prompt type, invalidation on model version bumps, and cache hit tracking via Analytics Engine.

---

## Context

Cloudflare KV is a globally-distributed key-value store with eventual consistency and per-key TTL. It is ideal for prompt caching because:

- Read latency is ~1–5 ms from the nearest PoP.
- Values up to 25 MB (plenty for LLM responses).
- Per-key TTL handles natural expiry without a separate eviction job.
- Writes are cheap; the hot path is always a read.

The tradeoff: KV is eventually consistent, so a cache write in one region may not be visible in another for up to 60 seconds. For prompt caching this is acceptable — stale completions are still valid completions.

---

## Solution

```typescript
// src/index.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  AI: Ai;
  PROMPT_CACHE: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset; // optional — remove if not using AE
}

// ── Cache key generation ─────────────────────────────────────────────────────
// Keys encode model + canonical prompt so a model upgrade busts old entries.

interface CacheKeyInput {
  model: string;
  messages: Array<{ role: string; content: string }>;
  temperature?: number;
}

async function buildCacheKey(input: CacheKeyInput): Promise<string> {
  // Canonicalise: strip whitespace differences, sort deterministic fields.
  const canonical = JSON.stringify({
    model: input.model,
    // temperature affects output distribution — include it in the key.
    temperature: input.temperature ?? 0,
    messages: input.messages.map((m) => ({
      role: m.role,
      // Normalise whitespace so 'hello  world' and 'hello world' hit the same key.
      content: m.content.replace(/\s+/g, ' ').trim(),
    })),
  });

  // SHA-256 via Web Crypto — available in all Workers runtimes.
  const encoded = new TextEncoder().encode(canonical);
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');

  // Prefix with model slug for debuggability in KV explorer.
  const modelSlug = input.model.replace(/[^a-z0-9]/gi, '-').slice(0, 40);
  return `cache:${modelSlug}:${hex}`;
}

// ── TTL strategy ─────────────────────────────────────────────────────────────
// Different prompt classes have different staleness tolerances.

type PromptClass = 'faq' | 'creative' | 'realtime' | 'default';

const TTL_SECONDS: Record<PromptClass, number> = {
  faq:      60 * 60 * 24 * 7,  // 7 days  — stable Q&A
  creative: 60 * 60 * 1,       // 1 hour  — creative outputs should vary
  realtime: 60 * 5,            // 5 mins  — news / live data context
  default:  60 * 60 * 6,       // 6 hours — general purpose
};

function classifyPrompt(systemPrompt: string): PromptClass {
  const lower = systemPrompt.toLowerCase();
  if (lower.includes('faq') || lower.includes('knowledge base')) return 'faq';
  if (lower.includes('creative') || lower.includes('story')) return 'creative';
  if (lower.includes('live') || lower.includes('real-time') || lower.includes('news')) return 'realtime';
  return 'default';
}

// ── Cached inference call ────────────────────────────────────────────────────

interface InferenceOptions {
  model: string;
  messages: Array<{ role: string; content: string }>;
  temperature?: number;
  promptClass?: PromptClass;
}

interface CachedResponse {
  response: string;
  cacheHit: boolean;
  cacheKey: string;
  model: string;
}

async function cachedInfer(
  options: InferenceOptions,
  env: Env
): Promise<CachedResponse> {
  const { model, messages, temperature, promptClass } = options;
  const cacheKey = await buildCacheKey({ model, messages, temperature });

  // ── 1. Cache read (cache-aside pattern) ─────────────────────────────────
  const cached = await env.PROMPT_CACHE.get(cacheKey, { type: 'text' });
  if (cached !== null) {
    trackCacheEvent('hit', model, env);
    return { response: cached, cacheHit: true, cacheKey, model };
  }

  // ── 2. Cache miss — call model ───────────────────────────────────────────
  const result = await env.AI.run(model as Parameters<Ai['run']>[0], {
    messages,
    temperature: temperature ?? 0,
    max_tokens: 2048,
  });

  const text: string =
    typeof result === 'string'
      ? result
      : (result as { response?: string }).response ?? JSON.stringify(result);

  // ── 3. Cache write ───────────────────────────────────────────────────────
  const systemContent =
    messages.find((m) => m.role === 'system')?.content ?? '';
  const cls = promptClass ?? classifyPrompt(systemContent);
  const ttl = TTL_SECONDS[cls];

  // Fire-and-forget: do not await the write so the response returns immediately.
  env.PROMPT_CACHE.put(cacheKey, text, { expirationTtl: ttl }).catch(
    (err) => console.error('KV put failed:', err)
  );

  trackCacheEvent('miss', model, env);
  return { response: text, cacheHit: false, cacheKey, model };
}

// ── Analytics Engine tracking ────────────────────────────────────────────────
// One data point per request — query with Workers Analytics Engine SQL API.

function trackCacheEvent(
  event: 'hit' | 'miss',
  model: string,
  env: Env
): void {
  try {
    env.ANALYTICS?.writeDataPoint({
      blobs:  [event, model],                         // blob1=event, blob2=model
      doubles: [event === 'hit' ? 1 : 0],             // double1=is_hit
      indexes: [model.slice(0, 32)],                  // shard index
    });
  } catch {
    // Analytics Engine is best-effort — never let it crash the request path.
  }
}

// ── Cache invalidation on model version change ───────────────────────────────
// KV has no prefix-delete. Strategy: encode a "cache epoch" in the key prefix
// and increment it when you deploy a new model version.

const CACHE_EPOCH = '1'; // bump this whenever the model checkpoint changes

async function buildVersionedCacheKey(input: CacheKeyInput): Promise<string> {
  const baseKey = await buildCacheKey(input);
  return `v${CACHE_EPOCH}:${baseKey}`;
}

// ── Cost savings helper ──────────────────────────────────────────────────────
// Workers AI pricing: ~$0.011 / 1k tokens (Llama 3.1 8B, as of mid-2025).
// Adjust COST_PER_1K_TOKENS to the current rate on your plan.

const COST_PER_1K_TOKENS = 0.011;

function estimateSavings(params: {
  totalRequests: number;
  hitRate: number;           // 0–1
  avgInputTokens: number;
  avgOutputTokens: number;
}): { savedUsd: string; callsDeflected: number } {
  const { totalRequests, hitRate, avgInputTokens, avgOutputTokens } = params;
  const callsDeflected = Math.floor(totalRequests * hitRate);
  const tokensPerCall = avgInputTokens + avgOutputTokens;
  const savedUsd = (
    (callsDeflected * tokensPerCall * COST_PER_1K_TOKENS) / 1000
  ).toFixed(4);
  return { savedUsd, callsDeflected };
}

// ── Request handler ───────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const body = await request.json<{
      model?: string;
      messages: Array<{ role: string; content: string }>;
      temperature?: number;
      prompt_class?: PromptClass;
    }>();

    const model = body.model ?? '@cf/meta/llama-3.1-8b-instruct';

    const result = await cachedInfer(
      {
        model,
        messages: body.messages,
        temperature: body.temperature,
        promptClass: body.prompt_class,
      },
      env
    );

    return Response.json({
      response:  result.response,
      cache_hit: result.cacheHit,
      cache_key: result.cacheKey,
    });
  },
};
```

### wrangler.toml additions

```toml
[[kv_namespaces]]
binding = "PROMPT_CACHE"
id      = "<your-kv-namespace-id>"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "prompt_cache_events"
```

---

## Implementation Details

**Cache key uniqueness**: SHA-256 of the canonical JSON is collision-resistant for all practical purposes. Include `temperature` in the key because a temperature of 0 vs 0.9 produces deterministically different distributions — caching across temperatures would serve wrong results.

**Fire-and-forget write**: The `await env.PROMPT_CACHE.put(...)` is intentionally not awaited. The response returns to the client immediately after inference. If the write fails (rare KV hiccup), the next request simply gets another cache miss and tries again.

**TTL calibration**: Start with the defaults in `TTL_SECONDS` and adjust based on hit rate data from Analytics Engine. FAQ content rarely changes; 7-day TTL yields high hit rates. Creative prompts should expire quickly so users don't keep getting identical outputs.

**Cache epoch invalidation**: When you deploy a new model checkpoint (e.g. `llama-3.1-8b` → `llama-3.2-8b`) the old keys are harmless — they simply expire on their TTL. For immediate invalidation, bump `CACHE_EPOCH` from `'1'` to `'2'`. Old keys are orphaned and will expire naturally.

**Hit rate query** (Analytics Engine SQL):

```sql
SELECT
  SUM(double1) AS hits,
  COUNT(*)     AS total,
  ROUND(SUM(double1) / COUNT(*) * 100, 2) AS hit_rate_pct
FROM prompt_cache_events
WHERE timestamp > NOW() - INTERVAL '1' DAY
```

---

## Anti-patterns

- **Caching with `temperature > 0` and expecting identical outputs**: The cache key includes temperature, but the model output at `t > 0` is non-deterministic. Cache if you want to avoid re-invoking the model at all; don't cache if variety per user is important.
- **Storing entire conversation history in the cache key**: Only cache single-turn prompts or summarised context. Full multi-turn history rarely repeats exactly and pollutes KV with one-time keys.
- **Awaiting the KV write on the critical path**: This adds 5–15 ms to every cache-miss response. Fire and forget.
- **Using the raw prompt string as a KV key**: KV keys have a 512-byte limit. A long system prompt will exceed it. Always hash.
- **Not tracking hit rate**: Without telemetry you cannot justify the caching layer or tune TTLs.

---

## Gotchas

- KV `get` returns `null` for a missing key, not `undefined`. Check `!== null` not `!= null`.
- Workers AI can return different response shapes depending on the model (string vs `{ response: string }`). The `text` extraction logic must handle both.
- If `ANALYTICS` is not bound (e.g. local dev), `env.ANALYTICS?.writeDataPoint` silently no-ops because of the optional chain.
- KV has a 1 GB per-namespace soft limit in the free tier; prompt cache values are small but high-volume deployments should set a generous TTL so stale keys self-evict.
- `expirationTtl` minimum is 60 seconds — you cannot cache for less than one minute.

---

## Verification

```bash
# First call — expect cache_hit: false
curl -s -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is 2+2?"}]}' | jq .cache_hit

# Second identical call — expect cache_hit: true
curl -s -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is 2+2?"}]}' | jq .cache_hit

# Inspect KV keys via Wrangler
npx wrangler kv key list --binding PROMPT_CACHE
```

---

## Related

- `documentation/docs/policies/ai-ml/workers-ai-function-calling-tool-use.md` — cache tool result messages
- `documentation/docs/policies/ai-ml/workers-ai-reranking-search-results.md` — cache reranker scores
- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Workers Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/

---

## Sources

- Cloudflare KV API reference (2025)
- Workers AI pricing page (mid-2025)
- Cloudflare Analytics Engine SQL API docs
