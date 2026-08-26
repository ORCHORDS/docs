# Workers AI Model Fallback Chain for Resilience

date: 2026-08-24 / author: example.com / status: production

---

## Symptom / Use-case

A Workers AI inference call returns an error or times out — model overloaded, capacity limits hit, or a
specific model temporarily unavailable. Without a fallback strategy the Worker returns a 500 to the
client. You want automatic retry across a ranked list of alternative models so the end-user sees a
successful response even when the primary model is degraded.

## Context

Cloudflare Workers AI exposes multiple text-generation models (Llama variants, Mistral, Phi, Gemma,
etc.) with similar capabilities. A fallback chain tries each model in priority order, records which
model ultimately served the request, and returns the first successful result. The chain must handle
transient errors (`overloaded`, `rate_limit`, network timeouts) differently from permanent errors
(`invalid_input`, `content_policy`) that should not be retried on a different model.

Durable Objects or KV can optionally track per-model health state so degraded models are skipped
immediately rather than burning latency on known-bad endpoints. For stateless fallback the simple
sequential approach adds only milliseconds of overhead relative to a full model inference call.

---

## Define the fallback chain

```typescript
// src/fallback-chain.ts
export interface ModelConfig {
  modelId: string;
  maxTokens: number;
  temperature?: number;
}

export const TEXT_GENERATION_CHAIN: ModelConfig[] = [
  { modelId: "@cf/meta/llama-3.1-8b-instruct",      maxTokens: 2048, temperature: 0.7 },
  { modelId: "@cf/mistral/mistral-7b-instruct-v0.1", maxTokens: 2048, temperature: 0.7 },
  { modelId: "@cf/google/gemma-7b-it",               maxTokens: 1024, temperature: 0.7 },
  { modelId: "@cf/microsoft/phi-2",                  maxTokens: 512,  temperature: 0.7 },
];

// Errors that should NOT trigger a model switch — they won't improve on a different model
export const PERMANENT_ERROR_CODES = new Set([
  "content_policy_violation",
  "invalid_input",
  "context_length_exceeded",
]);

export function isPermanentError(err: unknown): boolean {
  if (err instanceof Error) {
    return PERMANENT_ERROR_CODES.has((err as any).code) ||
           err.message.includes("content policy") ||
           err.message.includes("invalid input");
  }
  return false;
}
```

---

## Core fallback executor

```typescript
// src/inference.ts
import { TEXT_GENERATION_CHAIN, isPermanentError, type ModelConfig } from "./fallback-chain";

export interface FallbackResult {
  response: string;
  modelUsed: string;
  attemptCount: number;
  errors: Array<{ model: string; error: string }>;
}

export async function runWithFallback(
  ai: Ai,
  messages: Array<{ role: string; content: string }>,
  timeoutMs = 25_000,
): Promise<FallbackResult> {
  const errors: FallbackResult["errors"] = [];

  for (const [index, config] of TEXT_GENERATION_CHAIN.entries()) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const result = await ai.run(config.modelId as any, {
        messages,
        max_tokens: config.maxTokens,
        temperature: config.temperature,
      });

      clearTimeout(timer);

      const text =
        typeof result === "object" && result !== null && "response" in result
          ? String((result as any).response)
          : String(result);

      return {
        response: text,
        modelUsed: config.modelId,
        attemptCount: index + 1,
        errors,
      };
    } catch (err) {
      clearTimeout(timer);

      const message = err instanceof Error ? err.message : String(err);
      errors.push({ model: config.modelId, error: message });

      // Do not try remaining models for permanent errors
      if (isPermanentError(err)) {
        throw new Error(`Permanent error on model ${config.modelId}: ${message}`);
      }

      // Last model in the chain — surface the accumulated errors
      if (index === TEXT_GENERATION_CHAIN.length - 1) {
        throw new Error(
          `All models exhausted. Errors: ${JSON.stringify(errors)}`,
        );
      }

      // Brief pause before trying the next model to avoid thundering-herd
      await new Promise((r) => setTimeout(r, 200 * (index + 1)));
    }
  }

  throw new Error("Unreachable: fallback chain exhausted without throwing");
}
```

---

## Worker entry point with observability headers

```typescript
// src/index.ts
import { runWithFallback } from "./inference";

export interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    let body: { messages: Array<{ role: string; content: string }> };
    try {
      body = await request.json();
    } catch {
      return new Response(JSON.stringify({ error: "Invalid JSON" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (!Array.isArray(body?.messages)) {
      return new Response(JSON.stringify({ error: "messages array required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    try {
      const result = await runWithFallback(env.AI, body.messages);

      return new Response(
        JSON.stringify({ response: result.response, model: result.modelUsed }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "X-Model-Used": result.modelUsed,
            "X-Attempt-Count": String(result.attemptCount),
          },
        },
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      return new Response(JSON.stringify({ error: message }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }
  },
};
```

---

## Optional: KV-based model health circuit breaker

```typescript
// src/health-kv.ts
const DEGRADED_TTL_SECONDS = 60; // skip a model for 60 s after failure

export async function markModelDegraded(kv: KVNamespace, modelId: string): Promise<void> {
  const key = `health:degraded:${modelId}`;
  await kv.put(key, "1", { expirationTtl: DEGRADED_TTL_SECONDS });
}

export async function isModelDegraded(kv: KVNamespace, modelId: string): Promise<boolean> {
  const key = `health:degraded:${modelId}`;
  return (await kv.get(key)) !== null;
}

// Integrate into runWithFallback: check isModelDegraded before each attempt,
// call markModelDegraded on transient failures, skip the model if degraded.
// This converts the sequential chain into an adaptive circuit-breaker chain.
export async function filterHealthyModels<T extends { modelId: string }>(
  kv: KVNamespace,
  chain: T[],
): Promise<T[]> {
  const checks = await Promise.all(
    chain.map(async (m) => ({ model: m, degraded: await isModelDegraded(kv, m.modelId) })),
  );
  const healthy = checks.filter((c) => !c.degraded).map((c) => c.model);
  // Always keep at least one model (the last healthy or fallback to full chain)
  return healthy.length > 0 ? healthy : chain;
}
```

---

## Analytics: log fallback events to Analytics Engine

```typescript
// src/analytics.ts
export interface Env {
  AI_FALLBACK_AE: AnalyticsEngineDataset;
}

export function recordFallbackEvent(
  ae: AnalyticsEngineDataset,
  modelUsed: string,
  attemptCount: number,
  durationMs: number,
): void {
  ae.writeDataPoint({
    blobs: [modelUsed],
    doubles: [attemptCount, durationMs],
    indexes: [modelUsed],
  });
}
```

## Anti-patterns

- **Retrying on permanent errors** — content policy violations and invalid inputs will fail identically
  on every model; retrying wastes time and budget.
- **Equal timeouts across models** — smaller models respond faster; give the primary model more time
  and shrink the timeout for fallbacks to preserve overall request latency.
- **No jitter in retry delays** — deterministic delays cause synchronized retries across concurrent
  requests; add jitter (`delay * (0.5 + Math.random() * 0.5)`).
- **Treating all models as interchangeable** — capability gaps (context length, instruction following,
  reasoning quality) vary significantly; order the chain by capability, not alphabetically.
- **Ignoring the `modelUsed` field in responses** — callers should know when they received a fallback
  response; include the model in the response body or headers for client-side handling.

## Gotchas

- Workers AI binding calls run in the same 30-second CPU wall-clock budget as the Worker; four
  sequential model attempts each taking 8 s will hit the limit. Set per-model timeouts accordingly.
- The `Ai` binding does not expose HTTP status codes directly; error classification must be based on
  the error message string, which can change between API versions.
- Some models silently truncate output rather than returning an error when `max_tokens` is too large;
  validate response length in the caller if completeness matters.
- Streaming (`stream: true`) and fallback chains are incompatible unless you buffer the primary
  attempt before committing to stream — a half-sent SSE response cannot be retried.

## Verification

```bash
# Deploy and confirm fallback header on a successful call
curl -sX POST https://your-worker.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hello"}]}' \
  -D - | grep -E "X-Model-Used|X-Attempt-Count"

# Simulate primary failure by temporarily removing first model from chain,
# then check that X-Attempt-Count is 2
```

Run `wrangler tail` during load tests and watch for `attemptCount > 1` events to tune the chain.

## Related

- `ai-gateway-fallback-model-chain.md` — AI Gateway-level fallback (provider switching)
- `llm-fallback-provider-rotation.md` — provider-level rotation across OpenAI, Anthropic, etc.
- `ai-gateway-circuit-breaker-provider-failover.md` — circuit breaker at the gateway layer
- `workers-ai-model-benchmarking-latency-profiling.md` — baseline latency data for chain ordering
- `llm-retry-patterns.md` — exponential backoff and retry budgets

## Sources

- Cloudflare Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- Workers AI error handling: https://developers.cloudflare.com/workers-ai/
- Cloudflare Workers CPU limits: https://developers.cloudflare.com/workers/platform/limits/
