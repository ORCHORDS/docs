# AI Gateway Request Retry Exponential Backoff

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project backend Workers calling AI Gateway occasionally receive 429 (rate limit), 503 (upstream overload), or timeout errors when routing to OpenAI, Anthropic, or Workers AI. Without a structured retry policy, transient failures surface as user-visible errors on post generation, content suggestions, and moderation pipelines.

## Context

Cloudflare AI Gateway is a reverse proxy that sits between the Worker and the upstream AI provider. It enforces per-account rate limits and adds logging and caching. Retries must be implemented in the Worker because AI Gateway itself does not automatically retry failed upstream calls; it returns the upstream error verbatim to the caller.

## Architecture — Retry Envelope

A retry envelope wraps every AI Gateway `fetch` call. It classifies errors as retryable (429, 503, 504, network timeout) or terminal (400, 401, 422). Retryable errors receive jittered exponential backoff. Terminal errors are returned immediately to avoid burning the caller's budget on hopeless requests.

```typescript
// retry-types.ts
export interface RetryOptions {
  maxAttempts: number;    // default 4
  baseDelayMs: number;    // default 250
  maxDelayMs: number;     // default 8_000
  jitterFactor: number;   // default 0.3 — ±30% random jitter
  retryableStatuses: number[];
}

export const DEFAULT_RETRY_OPTIONS: RetryOptions = {
  maxAttempts: 4,
  baseDelayMs: 250,
  maxDelayMs: 8_000,
  jitterFactor: 0.3,
  retryableStatuses: [429, 500, 502, 503, 504],
};

export interface RetryOutcome<T> {
  value: T;
  attempts: number;
  lastStatus: number;
}
```

## Implementation — Core Retry Loop

The retry loop uses `crypto.getRandomValues` (available in Workers) for jitter to avoid synchronized retry storms across multiple Worker instances hitting the same upstream.

```typescript
// retry.ts
import { DEFAULT_RETRY_OPTIONS, RetryOptions, RetryOutcome } from './retry-types';

function jitteredDelay(attempt: number, opts: RetryOptions): number {
  const exponential = Math.min(
    opts.baseDelayMs * Math.pow(2, attempt),
    opts.maxDelayMs,
  );
  const jitter = (Math.random() * 2 - 1) * opts.jitterFactor * exponential;
  return Math.max(0, Math.floor(exponential + jitter));
}

export async function withRetry<T>(
  fn: () => Promise<{ response: Response; value: T }>,
  opts: Partial<RetryOptions> = {},
): Promise<RetryOutcome<T>> {
  const o = { ...DEFAULT_RETRY_OPTIONS, ...opts };
  let lastError: unknown;
  let lastStatus = 0;

  for (let attempt = 0; attempt < o.maxAttempts; attempt++) {
    try {
      const result = await fn();
      lastStatus = result.response.status;

      if (!o.retryableStatuses.includes(result.response.status)) {
        return { value: result.value, attempts: attempt + 1, lastStatus };
      }

      // Retryable HTTP status — honour Retry-After header if present
      const retryAfter = result.response.headers.get('Retry-After');
      const delayMs = retryAfter
        ? Math.min(parseFloat(retryAfter) * 1000, o.maxDelayMs)
        : jitteredDelay(attempt, o);

      if (attempt < o.maxAttempts - 1) {
        await scheduler.wait(delayMs);
      }

      lastError = new Error(`HTTP ${result.response.status}`);
    } catch (err) {
      // Network-level errors (fetch timeout, DNS, TLS)
      lastError = err;
      lastStatus = 0;
      if (attempt < o.maxAttempts - 1) {
        await scheduler.wait(jitteredDelay(attempt, o));
      }
    }
  }

  throw Object.assign(
    new Error(`All ${o.maxAttempts} retry attempts failed`),
    { cause: lastError, lastStatus },
  );
}
```

## Implementation — AI Gateway Call with Retry

Wrap the AI Gateway endpoint using the retry envelope. The AI Gateway URL is constructed from the account ID, gateway slug, and provider prefix.

```typescript
// ai-gateway-client.ts
import { withRetry } from './retry';

interface Env {
  CF_ACCOUNT_ID: string;
  AI_GATEWAY_SLUG: string;    // e.g. "example project-gateway"
  OPENAI_API_KEY: string;
}

export async function chatCompletion(
  env: Env,
  messages: { role: string; content: string }[],
  model = 'gpt-4o-mini',
): Promise<string> {
  const gatewayBase = `https://gateway.ai.cloudflare.com/v1/${env.CF_ACCOUNT_ID}/${env.AI_GATEWAY_SLUG}/openai`;

  const outcome = await withRetry(async () => {
    const response = await fetch(`${gatewayBase}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${env.OPENAI_API_KEY}`,
        'cf-aig-metadata': JSON.stringify({ source: 'example project-worker' }),
      },
      body: JSON.stringify({ model, messages }),
      signal: AbortSignal.timeout(15_000), // 15 s hard cap
    });

    if (!response.ok && !DEFAULT_RETRY_OPTIONS.retryableStatuses.includes(response.status)) {
      const body = await response.text();
      throw Object.assign(new Error(`Terminal error ${response.status}`), { body });
    }

    const value = response.ok ? await response.json() as { choices: { message: { content: string } }[] } : null as never;
    return { response, value };
  });

  return outcome.value.choices[0].message.content;
}
```

## Optimization — Budget-Aware Early Abort

Track cumulative retry delay against a per-request budget. If retries would consume more time than the Worker's CPU budget (50 ms CPU for free tier, ~30 s wall clock), abort early and return a cached or degraded response.

```typescript
// budget-aware-retry.ts
export async function budgetAwareChat(
  env: Env,
  messages: { role: string; content: string }[],
  wallClockBudgetMs = 12_000,
): Promise<string | null> {
  const deadline = Date.now() + wallClockBudgetMs;

  try {
    return await chatCompletion(env, messages);
  } catch (err) {
    if (Date.now() >= deadline) {
      // Exceeded budget — return null for caller to serve degraded UX
      console.warn('AI Gateway retry budget exhausted', { err });
      return null;
    }
    throw err;
  }
}
```

## Monitoring — Retry Telemetry to Analytics Engine

Emit retry count, final status, and total delay so the on-call team can detect provider degradation before user complaints arrive.

```typescript
// retry-telemetry.ts
export function emitRetryEvent(
  ae: AnalyticsEngineDataset,
  provider: string,
  outcome: { attempts: number; lastStatus: number },
  totalDelayMs: number,
): void {
  ae.writeDataPoint({
    blobs: [provider, String(outcome.lastStatus)],
    doubles: [outcome.attempts, totalDelayMs],
    indexes: [provider],
  });
}

// Alert rule: if p99(attempts) > 2 over a 5-minute window, page on-call
```

## Anti-patterns

- Retrying 401 (authentication) errors — the key is wrong; retry will not fix it and wastes quota.
- Using `setTimeout` instead of `scheduler.wait` in Workers — `setTimeout` is not available in the Workers runtime outside of the compatibility flag; `scheduler.wait` is the correct primitive.
- Retrying without jitter — all Worker instances back off in lockstep and create a thundering-herd on the upstream provider at exactly the same moment.
- Setting `maxAttempts` above 5 for synchronous user-facing requests — the Worker's 30-second wall-clock limit means deep retry chains will terminate with a 1101 error rather than returning a response.
- Ignoring the `Retry-After` header on 429 responses — AI Gateway may forward the upstream provider's retry window, which should be respected over the calculated backoff.

## Gotchas

- `AbortSignal.timeout` is available in Workers runtime v3+ (compatibility date ≥ 2023-03-01); pin the compatibility date in `wrangler.toml`.
- AI Gateway adds its own request ID in `cf-aig-request-id` — log this on every attempt to correlate retry chains in Gateway's own logs.
- The Workers CPU time limit (50 ms / 30 s wall clock free tier) counts across all retry iterations; a retry on a slow upstream can violate the CPU budget even when individual calls are fast.
- AI Gateway rate limits are per-gateway, not per-Worker — multiple Workers sharing a gateway slug compete for the same quota.
- For Workers AI (not third-party), 429s indicate the global AI inference queue is full, not per-account rate limits; exponential backoff is appropriate but `maxDelayMs` should be capped at 4 s for time-sensitive paths.

## Verification

```typescript
// test/retry.test.ts
import { withRetry } from '../retry';

it('retries exactly 3 times on 429 then throws', async () => {
  let calls = 0;
  await expect(
    withRetry(async () => {
      calls++;
      const response = new Response(null, { status: 429, headers: {} });
      return { response, value: null as never };
    }, { maxAttempts: 3, baseDelayMs: 0, jitterFactor: 0 }),
  ).rejects.toThrow('All 3 retry attempts failed');
  expect(calls).toBe(3);
});
```

```bash
# Trigger a 429 manually via a tight rate-limit override in AI Gateway dashboard,
# then watch Analytics Engine for retry counts > 1
wrangler tail --format=pretty | grep 'retry'
```

## Related

- `documentation/categories/ai-ml/llm-retry-patterns.md`
- `documentation/categories/ai-ml/ai-gateway-rate-limiting.md`
- `documentation/categories/ai-ml/ai-gateway-fallback-model-chain.md`
- `documentation/categories/ai-ml/llm-timeout-handling.md`

## Sources

- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/workers/runtime-apis/scheduler/
- https://developers.cloudflare.com/ai-gateway/configuration/rate-limiting/
- https://developers.cloudflare.com/workers/platform/limits/
