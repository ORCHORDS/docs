# Backoff Cap Pattern — Workers Retry Strategy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker retries a failing upstream call with exponential backoff, but the calculated
delay keeps doubling until it exceeds the Workers wall-clock limit (30 s) or the
upstream's timeout window.  The Worker either errors out before attempting the final
retry, or holds open its subrequest budget waiting on a sleep that will never yield a
useful result.  Alternatively, a burst of simultaneous retries creates a thundering-herd
that hammers the recovering upstream in unison.

You need a **capped, jittered backoff** that stays within your wall-clock budget,
spreads retries across a time window to prevent stampedes, and gives up cleanly when
the cost of waiting exceeds the remaining opportunity.

---

## Context

"Exponential backoff" without a cap grows without bound: `2^n * baseMs` with n=10 is
over 17 minutes.  Workers cannot sleep for more than the remainder of their wall-clock
budget.  The canonical solution is to:

1. **Cap** the delay at a `maxDelayMs`.
2. **Jitter** the delay within `[0, cap]` (full-jitter) or `[cap/2, cap]`
   (equal-jitter) to spread simultaneous retriers.
3. **Deadline-gate** each attempt: abort if the remaining budget cannot accommodate the
   next delay plus a minimum attempt time.

This pattern pairs directly with the **Timeout Cascade Prevention** pattern; the
remaining deadline is fed into the backoff calculator to determine whether to retry
at all.

---

## Backoff Calculator

```typescript
// src/lib/backoff.ts

export interface BackoffOptions {
  /** Delay before first retry in ms (default: 100) */
  baseMs?: number;
  /** Longest any single delay should be in ms (default: 30_000) */
  maxDelayMs?: number;
  /** Jitter strategy: 'full' (default), 'equal', or 'none' */
  jitter?: 'full' | 'equal' | 'none';
  /** Multiplier per attempt (default: 2) */
  multiplier?: number;
}

/**
 * Returns the delay in ms for attempt number `attempt` (0-indexed: attempt=0 is the
 * first retry, i.e., after the initial request has already failed once).
 */
export function calcDelay(attempt: number, opts: BackoffOptions = {}): number {
  const base = opts.baseMs ?? 100;
  const cap = opts.maxDelayMs ?? 30_000;
  const mult = opts.multiplier ?? 2;
  const jitter = opts.jitter ?? 'full';

  // Exponential value, capped
  const expo = Math.min(cap, base * Math.pow(mult, attempt));

  switch (jitter) {
    case 'full':
      // Uniform sample in [0, expo] — lowest contention, highest spread
      return Math.random() * expo;
    case 'equal':
      // Uniform sample in [expo/2, expo] — bounded minimum delay
      return expo / 2 + Math.random() * (expo / 2);
    case 'none':
      return expo;
  }
}

/** Sleep for `ms` milliseconds using the Web Platform `scheduler.wait` or a Promise */
export async function sleep(ms: number): Promise<void> {
  if (ms <= 0) return;
  await new Promise<void>(resolve => setTimeout(resolve, ms));
}
```

---

## Retry Executor

```typescript
// src/lib/retry.ts
import { calcDelay, sleep, BackoffOptions } from './backoff';

export interface RetryOptions extends BackoffOptions {
  /** Maximum number of attempts (including the first try) */
  maxAttempts?: number;
  /** Absolute deadline in ms; retry is skipped if remaining budget < minBudgetMs */
  deadlineMs?: number;
  /** Minimum budget required to start a retry (default: 500 ms) */
  minBudgetMs?: number;
  /** Called before each retry — return false to abort early */
  onRetry?: (attempt: number, err: unknown, delayMs: number) => boolean | void;
  /** Classify an error as non-retryable (e.g., 400 Bad Request) */
  isRetryable?: (err: unknown) => boolean;
}

export class MaxAttemptsExceededError extends Error {
  constructor(public readonly cause: unknown, attempts: number) {
    super(`Failed after ${attempts} attempt(s)`);
    this.name = 'MaxAttemptsExceededError';
  }
}

/**
 * Executes `fn`, retrying with capped jittered backoff on error.
 * Respects an optional deadline: never starts a retry if remaining budget
 * is below `minBudgetMs`.
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  opts: RetryOptions = {},
): Promise<T> {
  const maxAttempts = opts.maxAttempts ?? 3;
  const minBudget = opts.minBudgetMs ?? 500;
  const isRetryable = opts.isRetryable ?? (() => true);
  let lastErr: unknown;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;

      // Non-retryable errors surface immediately
      if (!isRetryable(err)) throw err;

      const isLastAttempt = attempt === maxAttempts - 1;
      if (isLastAttempt) break;

      const delayMs = calcDelay(attempt, opts);

      // Deadline guard: skip retry if budget is insufficient
      if (opts.deadlineMs !== undefined) {
        const remaining = opts.deadlineMs - Date.now();
        if (remaining < delayMs + minBudget) {
          console.warn('Skipping retry: insufficient budget', {
            attempt,
            remainingMs: remaining,
            delayMs,
          });
          break;
        }
      }

      const shouldContinue = opts.onRetry?.(attempt, err, delayMs);
      if (shouldContinue === false) break;

      console.info('Retrying after error', { attempt, delayMs, error: String(err) });
      await sleep(delayMs);
    }
  }

  throw new MaxAttemptsExceededError(lastErr, maxAttempts);
}
```

---

## Classifying Retryable vs Non-Retryable Errors

```typescript
// src/lib/http-retryable.ts

/** HTTP status codes that are safe to retry */
const RETRYABLE_STATUSES = new Set([408, 429, 500, 502, 503, 504]);

export class HttpError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'HttpError';
  }
}

/** Use as `isRetryable` option in `withRetry` */
export function isHttpRetryable(err: unknown): boolean {
  if (err instanceof HttpError) return RETRYABLE_STATUSES.has(err.status);
  // Network errors (fetch failures) are retryable
  if (err instanceof TypeError && err.message.includes('fetch')) return true;
  return false;
}

/** Fetch wrapper that throws HttpError for non-2xx responses */
export async function checkedFetch(url: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new HttpError(res.status, `HTTP ${res.status}: ${body.slice(0, 200)}`);
  }
  return res;
}
```

---

## Usage in a Worker

```typescript
// src/workers/payment-caller.ts
import { withRetry } from '../lib/retry';
import { isHttpRetryable, checkedFetch } from '../lib/http-retryable';
import { fromRequest } from '../lib/deadline';

export interface Env {
  PAYMENT_API: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const ctx = fromRequest(req, 20_000);

    let response: Response;
    try {
      response = await withRetry(
        () => checkedFetch(`${env.PAYMENT_API}/charge`, {
          method: 'POST',
          body: req.body,
          headers: { 'Content-Type': 'application/json' },
        }),
        {
          maxAttempts: 4,
          baseMs: 200,
          maxDelayMs: 4_000,
          jitter: 'full',
          deadlineMs: ctx.deadlineMs,
          minBudgetMs: 800,
          isRetryable: isHttpRetryable,
          onRetry: (attempt, err, delayMs) => {
            console.warn('Payment retry', { attempt, delayMs, error: String(err) });
          },
        },
      );
    } catch (err) {
      const status = err instanceof Error && err.name === 'MaxAttemptsExceededError'
        ? 502 : 500;
      return new Response(JSON.stringify({ error: 'Payment failed', detail: String(err) }), {
        status,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(response.body, {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Observability: Retry Metrics

```typescript
// Emit structured retry events for Logpush / Workers Analytics Engine

interface RetryEvent {
  service: string;
  attempt: number;
  delayMs: number;
  outcome: 'retrying' | 'success' | 'exhausted';
  errorCode?: number;
}

function logRetry(env: { ANALYTICS: AnalyticsEngineDataset }, ev: RetryEvent): void {
  env.ANALYTICS.writeDataPoint({
    blobs: [ev.service, ev.outcome],
    doubles: [ev.attempt, ev.delayMs],
    indexes: [ev.service],
  });
}
```

---

## Jitter Strategy Comparison

| Strategy   | Delay range          | Best for                                    |
|------------|----------------------|---------------------------------------------|
| `full`     | [0, cap]             | Many simultaneous retriers; max spread      |
| `equal`    | [cap/2, cap]         | Guaranteed minimum wait; moderate spread    |
| `none`     | cap exactly          | Single caller, predictable timing           |

Full jitter is the default recommendation from AWS ("Exponential Backoff and Jitter"
blog post) for distributed systems with many concurrent retriers.

---

## Anti-patterns

- **Unbounded backoff** — `2^n * base` without a `maxDelayMs` cap; after 10 retries
  the delay is 1024× the base delay, exceeding any reasonable wall-clock budget.
- **No jitter** — all retriers hit the upstream at exactly the same instant after a
  shared outage, creating a retry storm that prevents recovery.
- **Retrying non-retryable errors** — retrying a 400 Bad Request wastes budget and
  delays the user's error response; always classify errors before retrying.
- **Ignoring the deadline** — starting a retry when only 50 ms remain before the
  gateway timeout guarantees a half-completed downstream call and a race condition.
- **Logging inside the sleep** — sleeping `delayMs` and then logging means your logs
  arrive after the delay; log before sleeping so observability is real-time.

---

## Gotchas

- **Workers do not have `setInterval`** — use repeated `setTimeout` calls (via the
  `sleep` helper) inside your retry loop; never assume a persistent process model.
- **`Math.random()` is not cryptographically random** — that is fine for jitter; do
  not use `crypto.getRandomValues()` here (slower, unnecessary).
- **Retry amplification** — if your Worker is itself called by a retrying client, each
  client retry triggers your internal retries; total upstream load = client retries ×
  worker retries.  Use circuit breakers to break the amplification loop.
- **Subrequest limits** — Workers on the Free plan allow 50 subrequests per request;
  `maxAttempts: 4` uses 4 of those.  On Paid plans the limit is 1000.
- **`sleep` in Durable Objects** — `sleep` via `setTimeout` works in DO handlers but
  pauses the DO's event loop; prefer the DO alarm API for long waits.

---

## Verification

```typescript
// test/retry.test.ts
import { withRetry, MaxAttemptsExceededError } from '../src/lib/retry';
import { vi, it, expect } from 'vitest';

it('retries up to maxAttempts and then throws', async () => {
  const fn = vi.fn().mockRejectedValue(new Error('flaky'));
  await expect(withRetry(fn, { maxAttempts: 3, baseMs: 0 }))
    .rejects.toBeInstanceOf(MaxAttemptsExceededError);
  expect(fn).toHaveBeenCalledTimes(3);
});

it('succeeds on second attempt', async () => {
  const fn = vi.fn()
    .mockRejectedValueOnce(new Error('first failure'))
    .mockResolvedValueOnce('ok');
  const result = await withRetry(fn, { maxAttempts: 3, baseMs: 0 });
  expect(result).toBe('ok');
  expect(fn).toHaveBeenCalledTimes(2);
});

it('skips retry when budget is insufficient', async () => {
  const fn = vi.fn().mockRejectedValue(new Error('always fails'));
  const deadline = { deadlineMs: Date.now() + 10 }; // nearly expired
  await expect(
    withRetry(fn, { maxAttempts: 5, baseMs: 200, deadlineMs: deadline.deadlineMs, minBudgetMs: 500 }),
  ).rejects.toBeInstanceOf(MaxAttemptsExceededError);
  expect(fn).toHaveBeenCalledTimes(1); // only the initial attempt
});
```

---

## Related

- `exponential-backoff-jitter-workers.md` — foundational backoff pattern
- `timeout-cascade-prevention-workers-fetch.md` — deadline propagation
- `circuit-breaker-workers-d1-fetch.md` — open the circuit after sustained failures
- `dead-letter-queue-pattern.md` — where messages go when retries are exhausted

---

## Sources

- "Exponential Backoff and Jitter" — AWS Architecture Blog
  https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Cloudflare Workers limits — subrequests per request
  https://developers.cloudflare.com/workers/platform/limits/#subrequests
- "Release It!" ch. 5 — timeouts and retries
  Michael T. Nygard, 2nd ed.
