# Workers AI Rate Limits: Lessons from Production

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

We integrated Workers AI for on-demand text generation, summarisation, and embedding generation in our content pipeline. Within the first week of a product launch:

- `@cf/meta/llama-3.1-8b-instruct` inference requests started returning `429 Too Many Requests` with no warning
- Burst traffic from a single viral post caused a cascade: rate limit → retry storm → rate limit amplified
- Our embedding generation pipeline stalled entirely during peak hours
- There was no visibility into current rate limit consumption — we were flying blind
- Fallback logic was absent; users saw raw 429 errors

This article records what we learned and the architecture that stabilised the pipeline.

---

## Context

Workers AI rate limits are **model-specific** and expressed in **neurons per minute** — a compute-unit Cloudflare uses to normalise across different model sizes. Each model class has its own limit:

- Smaller models (embedding, classification): high neuron budget, rarely hit
- Large language models (8B+ parameter): lower neuron budget, easy to exhaust at scale
- Image generation models: separate low limit bucket

Free-tier accounts have a strict global neuron cap. Paid accounts get higher limits but they are still finite and not automatically raised on traffic spikes.

Rate limit state is **per-account, not per-Worker**. All Workers in an account share the same bucket.

---

## Solution

### 1. AI Gateway as rate limit buffer and request deduplication layer

AI Gateway sits between your Worker and the Workers AI backend. It provides caching (semantic and exact), request logging, and built-in rate limit observability.

```typescript
// workers/src/ai-client.ts

interface Env {
  AI: Ai;
  AI_GATEWAY_ID: string; // set in wrangler.toml [vars]
}

interface InferenceOptions {
  prompt: string;
  maxTokens?: number;
  cacheKey?: string;
}

interface InferenceResult {
  text: string;
  fromCache: boolean;
}

export async function runInference(
  env: Env,
  options: InferenceOptions,
): Promise<InferenceResult> {
  const { prompt, maxTokens = 512, cacheKey } = options;

  // Route through AI Gateway for caching + observability
  const response = await env.AI.run(
    '@cf/meta/llama-3.1-8b-instruct',
    {
      prompt,
      max_tokens: maxTokens,
    },
    {
      gateway: {
        id: env.AI_GATEWAY_ID,
        // Cache identical prompts for 5 minutes to absorb duplicate requests
        cache_ttl: 300,
        // Skip cache for prompts with randomness flags
        skip_cache: cacheKey === undefined,
      },
    },
  );

  const result = response as { response: string };
  const fromCache = (response as Record<string, unknown>)['cached'] === true;

  return { text: result.response, fromCache };
}
```

### 2. Request queuing with exponential backoff

```typescript
// workers/src/ai-queue-handler.ts

interface Env {
  AI: Ai;
  AI_GATEWAY_ID: string;
  INFERENCE_RESULTS: KVNamespace;
}

interface InferenceJob {
  jobId: string;
  prompt: string;
  maxTokens: number;
  requestedAt: number;
}

export default {
  async queue(batch: MessageBatch<InferenceJob>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const job = message.body;

      // Skip jobs older than 5 minutes — caller has likely timed out
      if (Date.now() - job.requestedAt > 5 * 60 * 1000) {
        message.ack();
        continue;
      }

      try {
        const result = await runWithBackoff(
          () => env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
            prompt: job.prompt,
            max_tokens: job.maxTokens,
          }),
          { maxAttempts: 5, baseDelayMs: 2000 },
        );

        // Store result for the waiting client to poll
        await env.INFERENCE_RESULTS.put(
          `result:${job.jobId}`,
          JSON.stringify({ text: (result as { response: string }).response, completedAt: Date.now() }),
          { expirationTtl: 300 },
        );

        message.ack();
      } catch (err) {
        console.error(`Inference failed for job ${job.jobId}:`, err);
        // Let the Queue retry with its own backoff
        message.retry({ delaySeconds: 30 });
      }
    }
  },
} satisfies ExportedHandler<Env>;

interface BackoffOptions {
  maxAttempts: number;
  baseDelayMs: number;
}

async function runWithBackoff<T>(
  fn: () => Promise<T>,
  opts: BackoffOptions,
): Promise<T> {
  const { maxAttempts, baseDelayMs } = opts;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      const is429 = err instanceof Error && err.message.includes('429');

      if (!is429 || attempt === maxAttempts) throw err;

      // Exponential backoff with jitter
      const delay = baseDelayMs * 2 ** (attempt - 1) + Math.random() * 500;
      console.warn(`Rate limited (attempt ${attempt}/${maxAttempts}), retrying in ${Math.round(delay)}ms`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  throw new Error('unreachable');
}
```

### 3. Cached fallback for degraded mode

When inference is unavailable, serve the last cached result rather than surfacing an error:

```typescript
// workers/src/ai-with-fallback.ts

interface Env {
  AI: Ai;
  AI_GATEWAY_ID: string;
  INFERENCE_CACHE: KVNamespace;
}

export async function inferWithFallback(
  env: Env,
  prompt: string,
  cacheKey: string,
): Promise<{ text: string; stale: boolean }> {
  // Attempt live inference
  try {
    const response = await env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      { prompt, max_tokens: 512 },
      { gateway: { id: env.AI_GATEWAY_ID, cache_ttl: 600 } },
    );
    const text = (response as { response: string }).response;

    // Update cache on success
    await env.INFERENCE_CACHE.put(cacheKey, text, { expirationTtl: 3600 });
    return { text, stale: false };
  } catch (err) {
    // On rate limit or transient failure, serve stale cached response
    const cached = await env.INFERENCE_CACHE.get(cacheKey);
    if (cached) {
      console.warn('Serving stale AI response due to rate limit:', err);
      return { text: cached, stale: true };
    }
    // No cache, no service
    throw err;
  }
}
```

### 4. Embedding pipeline with batching

Embedding models have a higher neuron budget. Still, batching reduces round trips:

```typescript
// workers/src/embedding-pipeline.ts

interface Env {
  AI: Ai;
}

export async function embedTexts(
  env: Env,
  texts: string[],
): Promise<number[][]> {
  // Workers AI embedding models accept batches of up to 100 texts
  const BATCH_SIZE = 50;
  const results: number[][] = [];

  for (let i = 0; i < texts.length; i += BATCH_SIZE) {
    const batch = texts.slice(i, i + BATCH_SIZE);
    const response = await env.AI.run('@cf/baai/bge-small-en-v1.5', {
      text: batch,
    });
    const embeddings = (response as { data: number[][] }).data;
    results.push(...embeddings);
  }

  return results;
}
```

---

## Implementation Details

### Capacity planning approach

We instrument every AI call with a custom metric published via `ctx.waitUntil`:

```typescript
function logAiUsage(ctx: ExecutionContext, model: string, tokens: number): void {
  ctx.waitUntil(
    fetch('https://metrics.internal/ai-usage', {
      method: 'POST',
      body: JSON.stringify({ model, tokens, ts: Date.now() }),
    }).catch(() => { /* fire and forget */ }),
  );
}
```

After two weeks of data we mapped our token usage by hour and model, then sized the Queue consumer concurrency (`max_batch_size`, `max_retries`) to stay under 80% of the neuron budget at peak.

### Model selection heuristic

| Use-case | Model chosen | Reason |
|----------|-------------|--------|
| Short summarisation (<200 tokens) | `@cf/meta/llama-3.1-8b-instruct` | Good quality, lower cost |
| Long document Q&A | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Higher accuracy |
| Semantic search embeddings | `@cf/baai/bge-small-en-v1.5` | Fast, small, cheap |
| Text classification | `@cf/huggingface/distilbert-sst-2-int8` | Minimal neurons |

---

## Anti-patterns

- **Synchronous retry loops in the request path**: a 429 response during a user-facing request should enqueue for background processing, not retry in the same Worker invocation. Workers have a 30-second CPU limit.
- **Unbounded concurrency to the AI binding**: spawning 500 parallel `env.AI.run()` calls will exhaust the rate limit instantly and queue none of them.
- **No AI Gateway**: without Gateway you have no cache, no logs, no visibility into which prompts are being served and at what cost.
- **Treating all errors as retriable**: non-429 errors (e.g., model input validation) do not benefit from backoff; you'll waste neurons retrying requests that will always fail.
- **Ignoring the `cached` flag in Gateway responses**: cached responses cost no neurons. Tracking cache hit rate reveals whether AI Gateway is actually helping.

---

## Gotchas

- Rate limits are enforced globally across your Cloudflare account. A spike in one Workers project exhausts budget for all others.
- The `429` error from `env.AI.run()` is thrown as a JavaScript `Error` with a message string — there is no structured response body. Parse the message string to detect rate limits.
- AI Gateway caching is exact-match on the request body by default. Semantic caching requires opt-in and is not available for all models.
- Workers AI neuron costs are not available in real time from within a Worker — you can only read historical usage from the Cloudflare dashboard or Workers Analytics Engine.
- Queue consumer retries count against the same rate limit bucket. If your Queue consumer retries on 429, it can amplify the problem rather than smooth it.

---

## Verification

```typescript
// tests/ai-backoff.test.ts
import { describe, it, expect, vi } from 'vitest';

describe('runWithBackoff', () => {
  it('retries on 429 and succeeds on second attempt', async () => {
    let callCount = 0;
    const fn = vi.fn(async () => {
      callCount++;
      if (callCount === 1) throw new Error('Request failed: 429 Too Many Requests');
      return 'ok';
    });

    const { runWithBackoff } = await import('../src/ai-queue-handler');
    const result = await runWithBackoff(fn, { maxAttempts: 3, baseDelayMs: 10 });
    expect(result).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('throws after maxAttempts exhausted', async () => {
    const fn = vi.fn(async () => { throw new Error('429'); });
    const { runWithBackoff } = await import('../src/ai-queue-handler');
    await expect(runWithBackoff(fn, { maxAttempts: 2, baseDelayMs: 10 })).rejects.toThrow('429');
    expect(fn).toHaveBeenCalledTimes(2);
  });
});
```

---

## Related

- `documentation/categories/lessons/workers-queue-consumer-backpressure-lessons.md`
- `documentation/categories/lessons/kv-cache-stampede-lessons.md`
- `documentation/categories/lessons/d1-time-travel-recovery-lessons.md`

---

## Sources

- Workers AI rate limits: https://developers.cloudflare.com/workers-ai/platform/limits/
- AI Gateway caching: https://developers.cloudflare.com/ai-gateway/get-started/
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
