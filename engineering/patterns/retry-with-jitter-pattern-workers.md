# Retry with Exponential Backoff and Jitter in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker calls an external HTTP dependency that occasionally returns 429 or 503 responses. Naive immediate retries cause thundering-herd spikes that make the dependency worse. You need a retry helper with exponential backoff, full jitter, distinguishable retryable vs. fatal errors, and observability into attempt metrics.

---

## Context

Exponential backoff grows the wait time between retries geometrically, reducing load during outages. Adding full jitter (randomizing the delay uniformly between 0 and the computed cap) prevents synchronized retry storms when many Workers fire at the same time. The helper uses `scheduler.wait()` (Cloudflare's non-blocking sleep) so the Worker does not spin. Retryable HTTP status codes (429, 500, 502, 503, 504) are distinguished from fatal ones (400, 401, 403, 404, 422), which should not be retried. Each attempt is recorded to Analytics Engine for SLO dashboards. The helper integrates with the bulkhead DO pattern to apply circuit-breaker semantics.

---

## Implementation — Core Retry Helper

```typescript
// src/lib/retry.ts

export interface RetryOptions {
  maxAttempts: number;
  baseDelayMs: number;
  maxDelayMs: number;
  jitter: 'full' | 'equal' | 'none';
  retryableStatuses?: number[];
  onAttempt?: (attempt: AttemptEvent) => void | Promise<void>;
}

export interface AttemptEvent {
  attempt: number;
  delayMs: number;
  error?: Error;
  status?: number;
  retrying: boolean;
}

const DEFAULT_RETRYABLE_STATUSES = [429, 500, 502, 503, 504];
const FATAL_STATUSES = new Set([400, 401, 403, 404, 408, 409, 410, 422]);

export class RetryableError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly retryAfterMs?: number,
  ) {
    super(message);
    this.name = 'RetryableError';
  }
}

export class FatalError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = 'FatalError';
  }
}

function computeDelay(
  attempt: number,
  options: RetryOptions,
  retryAfterMs?: number,
): number {
  if (retryAfterMs !== undefined) {
    return Math.min(retryAfterMs, options.maxDelayMs);
  }

  const exponential = Math.min(
    options.baseDelayMs * 2 ** (attempt - 1),
    options.maxDelayMs,
  );

  switch (options.jitter) {
    case 'full':
      return Math.random() * exponential;
    case 'equal':
      return exponential / 2 + Math.random() * (exponential / 2);
    case 'none':
    default:
      return exponential;
  }
}

export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  options: RetryOptions,
): Promise<T> {
  const retryable = new Set(
    options.retryableStatuses ?? DEFAULT_RETRYABLE_STATUSES,
  );

  let lastError: Error | undefined;

  for (let attempt = 1; attempt <= options.maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err: any) {
      lastError = err;

      // Fatal errors — do not retry
      if (err instanceof FatalError) throw err;
      if (err.status !== undefined && FATAL_STATUSES.has(err.status)) {
        throw new FatalError(err.message, err.status);
      }

      const isRetryable =
        err instanceof RetryableError ||
        (err.status !== undefined && retryable.has(err.status)) ||
        err.name === 'TypeError'; // network errors (fetch failed)

      if (!isRetryable || attempt === options.maxAttempts) {
        break;
      }

      const delayMs = computeDelay(
        attempt,
        options,
        err instanceof RetryableError ? err.retryAfterMs : undefined,
      );

      const event: AttemptEvent = {
        attempt,
        delayMs,
        error: err,
        status: err.status,
        retrying: true,
      };

      if (options.onAttempt) await options.onAttempt(event);

      await scheduler.wait(delayMs);
    }
  }

  throw lastError ?? new Error('retryWithBackoff: exhausted all attempts');
}
```

---

## Implementation — HTTP Fetch Wrapper

```typescript
// src/lib/resilient-fetch.ts
import { retryWithBackoff, RetryableError, FatalError, RetryOptions } from './retry';
import { Env } from '../types';

export async function resilientFetch(
  url: string,
  init: RequestInit,
  env: Env,
  retryOptions: Partial<RetryOptions> = {},
): Promise<Response> {
  const options: RetryOptions = {
    maxAttempts: 5,
    baseDelayMs: 100,
    maxDelayMs: 30_000,
    jitter: 'full',
    onAttempt: (event) => {
      // Record attempt to Analytics Engine
      env.METRICS.writeDataPoint({
        blobs: [
          url,
          event.error?.name ?? 'unknown',
          String(event.status ?? 0),
          event.retrying ? 'retrying' : 'final',
        ],
        doubles: [event.attempt, event.delayMs],
        indexes: [new URL(url).hostname],
      });
    },
    ...retryOptions,
  };

  return retryWithBackoff(async () => {
    let response: Response;
    try {
      response = await fetch(url, init);
    } catch (networkErr: any) {
      // TypeError = fetch failed (DNS, connection refused, etc.) — retryable
      throw networkErr;
    }

    if (response.ok) return response;

    const retryAfterHeader = response.headers.get('Retry-After');
    const retryAfterMs = retryAfterHeader
      ? parseRetryAfter(retryAfterHeader)
      : undefined;

    if ([429, 500, 502, 503, 504].includes(response.status)) {
      throw new RetryableError(
        `HTTP ${response.status}`,
        response.status,
        retryAfterMs,
      );
    }

    throw new FatalError(`HTTP ${response.status}`, response.status);
  }, options);
}

function parseRetryAfter(header: string): number {
  const seconds = parseInt(header, 10);
  if (!isNaN(seconds)) return seconds * 1000;
  const date = Date.parse(header);
  if (!isNaN(date)) return Math.max(0, date - Date.now());
  return 0;
}
```

---

## Integration — Circuit Breaker Stub and Usage Example

```typescript
// src/handlers/fetch-product.ts
import { resilientFetch } from '../lib/resilient-fetch';
import { withBulkhead } from '../lib/bulkhead-client';
import { Env } from '../types';

export async function handleFetchProduct(
  request: Request,
  env: Env,
): Promise<Response> {
  const productId = new URL(request.url).pathname.split('/').at(-1);

  try {
    const response = await withBulkhead(
      env,
      'product-api',
      () =>
        resilientFetch(
          `https://product-api.internal.example.com/products/${productId}`,
          { method: 'GET', headers: { Authorization: `Bearer ${env.PRODUCT_API_KEY}` } },
          env,
          { maxAttempts: 4, baseDelayMs: 200 },
        ),
      { maxConcurrent: 20, timeoutMs: 8000 },
    );

    return Response.json(await response.json(), { status: response.status });
  } catch (err: any) {
    if (err.name === 'FatalError') {
      return Response.json({ error: 'invalid request' }, { status: err.status ?? 400 });
    }
    return Response.json(
      { error: 'upstream unavailable' },
      { status: 502 },
    );
  }
}
```

---

## Testing — Retry Logic Unit Tests

```typescript
// test/retry.spec.ts (Vitest)
import { describe, it, expect, vi } from 'vitest';
import { retryWithBackoff, RetryableError, FatalError } from '../src/lib/retry';

// Stub scheduler.wait so tests don't actually sleep
vi.stubGlobal('scheduler', { wait: vi.fn().mockResolvedValue(undefined) });

describe('retryWithBackoff', () => {
  it('returns immediately on success', async () => {
    const fn = vi.fn().mockResolvedValue('ok');
    expect(await retryWithBackoff(fn, { maxAttempts: 3, baseDelayMs: 10, maxDelayMs: 1000, jitter: 'none' })).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('retries on RetryableError and succeeds on second attempt', async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new RetryableError('429', 429))
      .mockResolvedValue('ok');
    expect(await retryWithBackoff(fn, { maxAttempts: 3, baseDelayMs: 10, maxDelayMs: 1000, jitter: 'none' })).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('throws FatalError immediately without retrying', async () => {
    const fn = vi.fn().mockRejectedValue(new FatalError('422', 422));
    await expect(
      retryWithBackoff(fn, { maxAttempts: 5, baseDelayMs: 10, maxDelayMs: 1000, jitter: 'none' }),
    ).rejects.toThrow(FatalError);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('exhausts maxAttempts and throws last error', async () => {
    const fn = vi.fn().mockRejectedValue(new RetryableError('503', 503));
    await expect(
      retryWithBackoff(fn, { maxAttempts: 3, baseDelayMs: 10, maxDelayMs: 1000, jitter: 'none' }),
    ).rejects.toThrow('503');
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it('respects Retry-After delay from RetryableError', async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new RetryableError('429', 429, 2000))
      .mockResolvedValue('ok');
    await retryWithBackoff(fn, { maxAttempts: 3, baseDelayMs: 10, maxDelayMs: 30000, jitter: 'none' });
    expect(vi.mocked(scheduler.wait)).toHaveBeenCalledWith(2000);
  });
});
```

---

## Anti-patterns

- **Using `setTimeout` instead of `scheduler.wait()`** — `setTimeout` in Workers does not pause execution; `scheduler.wait()` is the correct non-blocking sleep primitive.
- **Retrying 400/401/422 errors** — these are client errors that won't resolve with retries; always distinguish fatal from transient errors.
- **Infinite retries without a max** — a stuck dependency causes the Worker to exhaust its 30-second CPU budget; always set `maxAttempts`.
- **No jitter** — deterministic backoff causes synchronized retry storms from many parallel Workers; always use `'full'` jitter in production.
- **Retrying inside a Queues consumer without returning an error** — Workers Queues handles retry natively; returning a thrown error from the consumer is cleaner than manual retry loops.

---

## Gotchas

- `scheduler.wait()` is only available in the Workers runtime with `compatibility_date >= 2023-10-02`; set it in `wrangler.toml`.
- The Workers CPU time limit is 30 seconds (50 ms on free plan); `maxDelayMs: 30000` combined with 5 attempts could theoretically breach the limit — keep total potential wait time well under 30 seconds.
- `Retry-After` headers can be an integer (seconds) or an HTTP date string; the `parseRetryAfter` helper handles both.
- Analytics Engine `writeDataPoint` is fire-and-forget; data appears in the SQL API within ~1 minute, not in real time.
- When using the bulkhead wrapper together with this retry helper, acquire a new bulkhead slot for each attempt, not once before the retry loop, to avoid holding a slot during the sleep window.

---

## Verification

```bash
# Run unit tests
npx vitest run test/retry.spec.ts

# Inspect retry metrics in Analytics Engine (last 10 minutes)
curl 'https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql' \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT blob4 AS outcome, count() AS cnt, avg(double2) AS avg_delay_ms \
      FROM metrics \
      WHERE timestamp > NOW() - INTERVAL '10' MINUTE \
      GROUP BY outcome ORDER BY cnt DESC"

# Tail live Worker logs during a load test
wrangler tail my-worker --format pretty | grep -E '(attempt|retrying|FatalError)'

# Verify scheduler.wait is available
wrangler dev --compatibility-date 2024-09-23 --test-scheduled
```

---

## Related

- `bulkhead-pattern-workers-concurrency-limit.md`
- `outbox-pattern-workers-d1-queues.md`
- `saga-pattern-workers-durable-objects.md`

---

## Sources

- Cloudflare Workers scheduler.wait() — https://developers.cloudflare.com/workers/runtime-apis/scheduler/
- AWS Architecture Blog — Exponential Backoff And Jitter — https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
