# Workers AI Model Warm-Up Request Priming
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Workers AI-powered endpoint produces p50 inference latency of 120 ms but p95 spikes to 2–4 s.
The pattern is worst after periods of low traffic (nights, weekends) and on the first request
following a new Workers deployment. Cold-start inference overhead—model weights loading into GPU
memory, worker isolate initialization, and AI gateway routing—dominates the tail latency
distribution.

## Context

Workers AI runs inference on Cloudflare's GPU-accelerated fleet. Models are loaded into GPU memory
on first use within a PoP (warm) and evicted under LRU pressure when idle. A cold model load adds
500 ms–3 s depending on model size (e.g., `@cf/meta/llama-3.1-8b-instruct` vs
`@cf/baai/bge-small-en-v1.5`). Unlike CPU Workers, model weight eviction is a GPU-memory
constraint, not a V8 isolate lifecycle event.

Priming is the practice of sending a synthetic low-cost request to a model before real traffic
arrives, keeping weights resident in GPU memory. Cloudflare Cron Triggers provide a native
scheduler for this without external infrastructure.

Key parameters:
- `max_tokens: 1` minimises time-to-first-token cost and billing for priming requests.
- Target PoPs that serve your users; priming one PoP does not warm others.
- Use `cf.colo` in the response to confirm which PoP served the priming request.

## Priming Worker (Cron Trigger)

```typescript
// src/index.ts
interface Env {
  AI: Ai;
  ANALYTICS: AnalyticsEngineDataset;
}

const PRIME_MODELS: Array<{ model: BaseAiTextGenerationModels; prompt: string }> = [
  {
    model: '@cf/meta/llama-3.1-8b-instruct',
    prompt: 'Reply with one word.',
  },
  {
    model: '@cf/mistral/mistral-7b-instruct-v0.1',
    prompt: 'Hi',
  },
];

async function primeModel(
  ai: Ai,
  model: BaseAiTextGenerationModels,
  prompt: string,
): Promise<{ model: string; latencyMs: number; error?: string }> {
  const start = Date.now();
  try {
    await ai.run(model, {
      messages: [{ role: 'user', content: prompt }],
      max_tokens: 1,
      stream: false,
    } as AiTextGenerationInput);
    return { model, latencyMs: Date.now() - start };
  } catch (err) {
    return {
      model,
      latencyMs: Date.now() - start,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

export default {
  // Regular HTTP handler — production inference
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/api/infer') {
      return new Response('Not found', { status: 404 });
    }

    const body = await request.json<{ prompt: string }>();
    const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [{ role: 'user', content: body.prompt }],
      max_tokens: 512,
      stream: false,
    } as AiTextGenerationInput);

    return Response.json(result);
  },

  // Scheduled priming — fires every 10 minutes via cron trigger
  async scheduled(
    _event: ScheduledEvent,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    ctx.waitUntil(runPriming(env));
  },
} satisfies ExportedHandler<Env>;

async function runPriming(env: Env): Promise<void> {
  const results = await Promise.allSettled(
    PRIME_MODELS.map(({ model, prompt }) => primeModel(env.AI, model, prompt)),
  );

  for (const result of results) {
    if (result.status === 'fulfilled') {
      const { model, latencyMs, error } = result.value;
      env.ANALYTICS.writeDataPoint({
        blobs: [model, error ?? 'ok'],
        doubles: [latencyMs],
        indexes: ['ai-warmup'],
      });
    }
  }
}
```

## wrangler.toml Configuration

```toml
name = "ai-inference-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[ai]
binding = "AI"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "ai_warmup_metrics"

# Fire every 10 minutes — keeps model warm across typical GPU eviction windows
[[triggers]]
crons = ["*/10 * * * *"]
```

## Adaptive Priming: Skip if Recently Warm

To avoid wasting inference tokens when the model is already warm, store the last prime timestamp
in KV and skip if within a recency window:

```typescript
// src/adaptive-prime.ts
interface AdaptivePrimeEnv extends Env {
  PRIME_STATE: KVNamespace;
}

const WARM_THRESHOLD_MS = 8 * 60 * 1000; // 8 minutes

export async function adaptivePrime(
  env: AdaptivePrimeEnv,
  model: BaseAiTextGenerationModels,
): Promise<'skipped' | 'primed' | 'error'> {
  const key = `prime-ts:${model}`;
  const lastPrimeStr = await env.PRIME_STATE.get(key);
  const lastPrime = lastPrimeStr ? parseInt(lastPrimeStr, 10) : 0;

  if (Date.now() - lastPrime < WARM_THRESHOLD_MS) {
    return 'skipped';
  }

  const { error } = await primeModel(env.AI, model, 'Hi');

  if (!error) {
    await env.PRIME_STATE.put(key, String(Date.now()), {
      expirationTtl: 3600,
    });
    return 'primed';
  }

  return 'error';
}
```

## Priming Embeddings Models

Embedding models have different cold-start profiles. Use a minimal single-input batch:

```typescript
async function primeEmbedding(ai: Ai): Promise<number> {
  const start = Date.now();
  await ai.run('@cf/baai/bge-small-en-v1.5', {
    text: ['warm'],
  });
  return Date.now() - start;
}
```

Embedding models are typically lighter (< 100 MB weights) and warm faster (<500 ms cold start)
but are called at higher QPS (RAG pipelines), making sustained warmth more valuable.

## Monitoring Warm vs Cold Latency

```typescript
// src/latency-classifier.ts
export function classifyLatency(ms: number, modelFamily: 'llm' | 'embed'): 'cold' | 'warm' {
  const coldThreshold = modelFamily === 'llm' ? 800 : 200;
  return ms > coldThreshold ? 'cold' : 'warm';
}
```

Emit `classification` as a blob to Analytics Engine. Alert when `cold` fraction exceeds 5% of
production requests—it indicates the priming interval is too long or the model is being
evicted between prime runs.

## Anti-patterns

- **Priming with `max_tokens: 512` or more**: priming tokens are billed. Use `max_tokens: 1` for
  the warmup prompt; the model weight loads before the first token is generated.
- **Using HTTP fetch to the AI binding**: always use the `env.AI` binding directly. Routing through
  an HTTP endpoint adds DNS + TLS overhead and may land on a different PoP than the one you want.
- **Priming in `fetch()` on the first request**: this blocks the response. Use cron triggers or a
  separate pre-warm endpoint with `ctx.waitUntil()`.
- **Relying on Cloudflare's AI Gateway cache as a substitute for warm weights**: the gateway caches
  *responses*, not model weights. A cached response is served from KV, not the GPU; it does not
  keep the model warm.
- **Priming all models in series**: serial priming adds latency to the cron run. Use
  `Promise.allSettled()` to parallelise across models as shown.

## Gotchas

- Cron triggers fire from a Cloudflare PoP, but not necessarily the same PoP your users hit. If
  your traffic concentrates in specific regions (e.g., EU), consider region-pinning via
  Workers Smart Placement or deploying a region-specific priming Worker.
- GPU memory eviction is opaque—there is no API to query whether a model is warm. Latency
  classification via threshold is the only observable signal.
- `max_tokens: 1` may return an empty string or a single punctuation character; do not validate
  priming responses for content.
- Model versions change on Cloudflare's schedule. Pin to a versioned model ID where possible
  (e.g., `@cf/meta/llama-3.1-8b-instruct`) rather than an alias that may rotate to a larger model.
- Free tier Workers AI has lower rate limits. Priming every 10 minutes across multiple models may
  exhaust free-tier quotas; adjust the cron interval accordingly.

## Verification

```bash
# Observe cold vs warm latency distribution over 24 hours
# After deploying the priming cron, query Analytics Engine:

SELECT
  blob2 AS status,
  quantileExact(0.5)(double1) AS p50_ms,
  quantileExact(0.95)(double1) AS p95_ms,
  count() AS samples
FROM ai_warmup_metrics
WHERE timestamp >= now() - INTERVAL 1 DAY
GROUP BY blob2
ORDER BY p95_ms DESC;

# p95 should drop from >2000 ms to <300 ms after priming stabilises.
```

```bash
# Confirm the scheduled Worker fires correctly
wrangler tail --format pretty ai-inference-worker | grep "ai-warmup"
```

## Related

- `workers-ai-inference-response-caching.md`
- `workers-ai-token-streaming-latency.md`
- `workers-cron-trigger-self-healing-retry.md`
- `workers-smart-placement-origin-latency.md`
- `cloudflare-observatory-rum-synthetic-gap-analysis.md`

## Sources

- Cloudflare Docs: Workers AI — https://developers.cloudflare.com/workers-ai/
- Cloudflare Docs: Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare Docs: Workers AI Models — https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Blog: Workers AI GA (2024) — https://blog.cloudflare.com/workers-ai-ga/
