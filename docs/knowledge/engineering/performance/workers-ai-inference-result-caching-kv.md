# Caching AI Inference Results in KV to Eliminate Repeat Calls

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker calls `env.AI.run()` on every request, even for identical or near-identical prompts. Inference is expensive (latency: 200–2000 ms; cost: billed per token). If the same prompt recurs — FAQ answers, product descriptions, moderation labels for common phrases — you are paying and waiting for the same result repeatedly.

## Context

Cloudflare Workers AI runs inference on Cloudflare's GPU fleet. Results for a given model + prompt combination are deterministic (at temperature 0) or near-deterministic (at low temperature). KV (Workers KV) is a globally replicated key-value store with sub-millisecond read latency at the edge, making it the natural caching layer for inference results.

Approach:
1. Hash the prompt (and model name) to a compact, safe KV key.
2. Check KV before calling `env.AI.run()`.
3. On a miss, call the model, store the result with a TTL, and return it.
4. Pre-warm the cache for predictable prompts via a Cron Trigger.
5. Emit hit/miss metrics to Analytics Engine for observability.

## `cachedInference` Wrapper

```typescript
import type { Ai } from '@cloudflare/workers-types';

interface Env {
  AI: Ai;
  INFERENCE_CACHE: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;
}

type AiTextGenerationOutput = {
  response?: string;
};

/** Compute a SHA-256 hex digest of a string using the Web Crypto API. */
async function sha256(input: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(input);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Run AI inference with KV caching.
 *
 * @param prompt   The user prompt.
 * @param model    Workers AI model ID, e.g. '@cf/meta/llama-3.1-8b-instruct'.
 * @param env      Worker environment bindings.
 * @param ttl      KV expiration in seconds (default: 1 hour).
 */
export async function cachedInference(
  prompt: string,
  model: string,
  env: Env,
  ttl = 3600
): Promise<string> {
  // 1. Derive a safe, deterministic KV key.
  const cacheKey = `ai:${model}:${await sha256(prompt)}`;

  // 2. Check cache.
  const cached = await env.INFERENCE_CACHE.get(cacheKey);
  if (cached !== null) {
    emitMetric(env, 'inference_cache_hit', model);
    return cached;
  }

  // 3. Cache miss — call the model.
  emitMetric(env, 'inference_cache_miss', model);
  const output = await env.AI.run(model, {
    messages: [{ role: 'user', content: prompt }],
  }) as AiTextGenerationOutput;

  const text = output.response ?? '';

  // 4. Persist with TTL.  KV `expirationTtl` must be >= 60 s.
  await env.INFERENCE_CACHE.put(cacheKey, text, { expirationTtl: ttl });

  return text;
}

/** Write a single-row event to Analytics Engine for hit-rate tracking. */
function emitMetric(
  env: Env,
  event: 'inference_cache_hit' | 'inference_cache_miss',
  model: string
): void {
  env.ANALYTICS.writeDataPoint({
    blobs: [event, model],
    doubles: [1],
    indexes: [event],
  });
}

// ─── Fetch handler ────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { searchParams } = new URL(request.url);
    const prompt = searchParams.get('prompt') ?? 'Summarise Cloudflare Workers in one sentence.';
    const model = '@cf/meta/llama-3.1-8b-instruct';

    const result = await cachedInference(prompt, model, env);
    return Response.json({ result });
  },

  // ─── Cache warming via Cron Trigger ────────────────────────────────────────
  //
  // In wrangler.toml:
  //   [[triggers.crons]]
  //   crons = ["0 * * * *"]   # hourly
  //
  // This handler pre-warms the cache for prompts that recur predictably
  // (e.g. the top-N FAQ questions fetched from D1).

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const WARM_PROMPTS = [
      'What is Cloudflare Workers?',
      'How does KV caching work?',
      'Explain D1 in one sentence.',
    ];
    const model = '@cf/meta/llama-3.1-8b-instruct';

    await Promise.all(
      WARM_PROMPTS.map((prompt) =>
        cachedInference(prompt, model, env, 7200) // 2-hour TTL for warmed entries
      )
    );
  },
};
```

## Choosing the Right TTL

| Content type | Suggested `expirationTtl` |
|---|---|
| Factual / product data | 3 600 s (1 hour) |
| News or time-sensitive | 300 s (5 minutes) |
| Pre-warmed FAQ answers | 7 200 s (2 hours) |
| Creative / per-user | Do not cache (non-deterministic) |

KV's minimum `expirationTtl` is 60 seconds. Passing a lower value throws a runtime error.

## Monitoring Cache Hit Rate with Analytics Engine

Analytics Engine events written via `writeDataPoint` are queryable with Workers Analytics Engine SQL API:

```sql
SELECT
  blob1 AS event,
  blob2 AS model,
  SUM(double1) AS count
FROM WORKERS_ANALYTICS
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY event, model
ORDER BY count DESC;
```

Target hit rate for stable FAQ-style prompts: > 80 %. If hit rate is low, increase TTL or broaden the prompt normalisation (e.g. lowercase, strip punctuation before hashing).

## Cache Warming Strategy

Cron Triggers (`scheduled` handler) run on Cloudflare's infrastructure without an incoming HTTP request. Use them to:
- Refresh expiring cache entries before they go cold.
- Fetch the top-N prompts from D1 and warm them ahead of peak traffic.
- Avoid thundering-herd on the first request after a cold deploy.

```toml
# wrangler.toml
[[triggers.crons]]
crons = ["0 * * * *"]  # every hour at :00
```

## Anti-patterns

- **Caching per-user or session-specific completions** — the hash will be unique per user context, giving a hit rate near 0 and wasting KV writes.
- **Using the raw prompt string as a KV key** — KV keys are limited to 512 bytes; long prompts exceed this. Always hash.
- **Setting `expirationTtl` below 60 s** — throws a KV API error at runtime.
- **Not cloning or serialising structured outputs** — `AI.run()` can return structured JSON for some models; store it with `JSON.stringify()` and parse on retrieval.

## Gotchas

- KV is **eventually consistent** — a write is visible globally within ~60 s. In the window after a write, some PoPs may still miss. This is acceptable for inference caching (the cost of a redundant inference call is low).
- SHA-256 produces a 64-character hex string. Combined with the model name prefix (`ai:@cf/meta/llama-3.1-8b-instruct:`), the key stays well under the 512-byte limit.
- `env.AI.run()` is billed per token even for repeated identical prompts — caching is the only way to avoid double-billing.
- Temperature > 0 produces non-deterministic outputs. Cache is still valid if you treat the first response as the canonical answer for that TTL window.

## Verification

```bash
# First request — expect MISS (observe latency ~500ms+)
curl -w "\nTime: %{time_total}s\n" \
  "https://my-worker.example.com/?prompt=What+is+Cloudflare+Workers"

# Second request — expect HIT (observe latency <50ms)
curl -w "\nTime: %{time_total}s\n" \
  "https://my-worker.example.com/?prompt=What+is+Cloudflare+Workers"

# Inspect KV directly
npx wrangler kv key list --binding INFERENCE_CACHE
npx wrangler kv key get --binding INFERENCE_CACHE "ai:@cf/meta/llama-3.1-8b-instruct:<hash>"
```

## Related

- `workers-cache-api-advanced-custom-keys.md`
- `cloudflare-tiered-cache-workers-origin-shield.md`
- `d1-batch-insert-performance-tuning.md`
- [Workers AI — Cloudflare Docs](https://developers.cloudflare.com/workers-ai/)
- [Workers KV — Cloudflare Docs](https://developers.cloudflare.com/kv/)

## Sources

- Cloudflare Workers AI documentation (2025)
- Cloudflare KV runtime API reference (2025)
- Cloudflare Analytics Engine SQL API documentation (2025)
