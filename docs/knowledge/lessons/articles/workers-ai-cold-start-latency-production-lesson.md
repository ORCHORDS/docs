# Workers AI Cold-Start Latency Surprise Production Lesson

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A production Workers endpoint calling `ai.run('@cf/meta/llama-3-8b-instruct')` returned
responses under 300 ms in local `wrangler dev` but spiked to 8-14 seconds on the first
request after any period of inactivity in production. p50 latency looked acceptable in
dashboards because steady-state was fast; p99 and cold-start percentiles were never
separately tracked. Users reported the feature as "broken" after the first request on any
low-traffic time-of-day window.

## Context

Cloudflare Workers AI runs inference on GPU-backed infrastructure. Models are not always
resident on the GPU attached to the nearest PoP. When a model hasn't been called recently
it must be loaded from storage into GPU VRAM — a process that can take several seconds
depending on model size. Smaller quantised models (`@cf/mistral/mistral-7b-instruct-v0.1`)
cold-start faster than 8B+ parameter models. The Workers runtime itself does not add
meaningful cold-start latency; the delay is entirely inside `ai.run()` while the model
loader initialises. Local `wrangler dev` uses a model stub that skips GPU loading entirely,
so no local signal exists for the production latency.

## Separate p99 and Cold-Start Tracking

Standard percentile dashboards average over all requests and hide rare but user-visible
spikes. Emit a custom metric for every `ai.run()` call that includes model name and whether
a configurable threshold was breached.

```typescript
// src/ai-with-telemetry.ts
export async function runWithLatencyTracking(
  ai: Ai,
  model: string,
  input: AiTextGenerationInput,
  ctx: ExecutionContext,
): Promise<AiTextGenerationOutput> {
  const start = Date.now();
  const result = await ai.run(model as BaseAiTextGenerationModels, input);
  const ms = Date.now() - start;

  const isColdStartLike = ms > 3000;
  ctx.waitUntil(
    fetch('https://analytics.example.com/ingest', {
      method: 'POST',
      body: JSON.stringify({ model, ms, cold: isColdStartLike, ts: Date.now() }),
    }),
  );
  return result;
}
```

## Warmup Cron Trigger

A lightweight cron Worker fires every 10 minutes calling each production model with a
minimal prompt. This keeps models resident in GPU VRAM during low-traffic periods.

```typescript
// src/warmup.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const models: BaseAiTextGenerationModels[] = [
      '@cf/meta/llama-3-8b-instruct',
      '@cf/mistral/mistral-7b-instruct-v0.1',
    ];
    await Promise.all(
      models.map((m) =>
        env.AI.run(m, { prompt: 'ping', max_tokens: 1 }).catch(() => {
          /* ignore errors from warmup probes */
        }),
      ),
    );
  },
} satisfies ExportedHandler<Env>;
```

## Timeout Guard and Graceful Degradation

Never let a cold-start block the HTTP response indefinitely. Set an explicit race against
`AbortSignal.timeout` and return a cached or placeholder response when inference is slow.

```typescript
// src/inference.ts
export async function inferWithTimeout(
  ai: Ai,
  model: BaseAiTextGenerationModels,
  input: AiTextGenerationInput,
  timeoutMs = 5000,
): Promise<AiTextGenerationOutput | null> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    // Workers AI does not yet propagate AbortSignal; use Promise.race instead
    const result = await Promise.race([
      ai.run(model, input),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('ai_timeout')), timeoutMs),
      ),
    ]);
    clearTimeout(timer);
    return result as AiTextGenerationOutput;
  } catch (err) {
    if ((err as Error).message === 'ai_timeout') return null;
    throw err;
  }
}
```

## Model Selection by Latency Budget

Choose the smallest model that meets quality requirements. Benchmark cold-start for each
candidate model in a staging Workers environment before committing to production.

```typescript
// src/model-router.ts
type LatencyTier = 'interactive' | 'background';

export function selectModel(tier: LatencyTier): BaseAiTextGenerationModels {
  // @cf/qwen/qwen1.5-1.8b-chat cold-starts ~1 s vs ~8 s for llama-3-8b
  return tier === 'interactive'
    ? '@cf/qwen/qwen1.5-1.8b-chat'
    : '@cf/meta/llama-3-8b-instruct';
}
```

## Streaming to Reduce Perceived Latency

Even when model loading takes several seconds, streaming tokens as they are generated
makes the user experience feel faster because the first token appears as soon as loading
completes rather than waiting for the full response.

```typescript
// src/stream.ts
export function streamInference(
  ai: Ai,
  model: BaseAiTextGenerationModels,
  prompt: string,
): ReadableStream {
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const enc = new TextEncoder();

  ai.run(model, { prompt, stream: true }).then(async (stream) => {
    for await (const chunk of stream as AsyncIterable<{ response?: string }>) {
      if (chunk.response) await writer.write(enc.encode(chunk.response));
    }
    await writer.close();
  });

  return readable;
}
```

## Anti-patterns

- Using `wrangler dev` latency as a proxy for production AI latency — the local stub skips
  GPU loading entirely.
- Tracking only p50 or p95 — cold-start events appear at p99+ and in first-request-of-hour
  segments that aggregated percentiles mask.
- Calling large models on interactive request paths without a timeout or fallback.
- Running warmup calls inside the hot path (`waitUntil` is fine; blocking `await` is not).

## Gotchas

- Cloudflare may evict a model from GPU memory at any time regardless of warmup frequency;
  warmup reduces frequency of cold-starts but cannot eliminate them.
- `stream: true` still waits for model loading before the first token arrives; it does not
  reduce cold-start duration, only perceived wait time after loading finishes.
- Workers AI pricing counts every token in warmup probe calls; use `max_tokens: 1` to
  minimise cost while still triggering model loading.
- `Promise.race` with a timeout leaves the AI call running in the background consuming
  resources; always wrap it in `ctx.waitUntil` so the Worker lifecycle covers the
  background inference even when the timeout path is taken.

## Verification

1. Deploy the warmup cron to production and observe p99 `ai.run()` latency over 24 hours.
2. Pause the cron for 20 minutes and send a request; verify the cold metric fires in your
   analytics pipeline.
3. Confirm the timeout guard returns `null` (not an exception) within `timeoutMs + 100 ms`
   by sending a request immediately after a forced eviction window.
4. Validate streaming: check that first-byte latency (TTFB) in browser DevTools shows
   content arriving before the full response completes.

## Related

- `workers-ai-rate-limit-exceeded-production-incident.md`
- `cache-cold-start-avalanche.md`
- `workers-cron-trigger-drift-missed-executions-postmortem.md`
- `timeouts-everywhere-no-exceptions.md`

## Sources

- Cloudflare Workers AI documentation — model catalog and inference limits
- Cloudflare Blog: "Workers AI is now generally available" (2024)
- Internal postmortem: example.com AI feature cold-start incident, Q1 2026
- Cloudflare Community: "Workers AI latency spikes on first call" thread
