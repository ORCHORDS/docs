# retry-with-exponential-backoff

**Issue:** Retry pattern with backoff, jitter, max attempts
**Date:** 2026-08-09
**Status:** documented

## Symptom
You call a vendor API. It returns 503. You immediately
retry. It returns 503. You retry. The vendor is
overwhelmed. You're part of the problem. The vendor
blocks your IP. Your service is down.

## Root cause
**Naive retry amplifies the problem.** When a vendor is
overloaded, every retry adds to the load. The vendor is
already struggling; your retries make it worse.

**Source:** AWS Architecture Blog — Exponential backoff:
https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

## The exponential backoff algorithm

For attempt N, wait:
- `2^N * baseDelay + jitter`
- Example: base 100ms, max 30s
  - Attempt 1: 100ms + jitter
  - Attempt 2: 200ms + jitter
  - Attempt 3: 400ms + jitter
  - ...
  - Attempt 10: 102400ms (~100s, capped at 30s) + jitter

```ts
async function withBackoff<T>(
  fn: () => Promise<T>,
  options: { maxAttempts?: number; baseDelayMs?: number; maxDelayMs?: number } = {}
): Promise<T> {
  const { maxAttempts = 5, baseDelayMs = 100, maxDelayMs = 30000 } = options;

  let lastError: Error | undefined;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err as Error;

      // Don't retry on the last attempt
      if (attempt === maxAttempts - 1) break;

      // Calculate delay
      const expDelay = Math.min(baseDelayMs * 2 ** attempt, maxDelayMs);
      const jitter = Math.random() * expDelay * 0.5;  // 0-50% jitter
      const delay = expDelay + jitter;

      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  throw lastError!;
}
```

## The "jitter" reason

Without jitter, all retries happen at the same time. A
thundering herd of clients all retry at the same moment,
overwhelming the vendor.

With jitter, retries are spread out:
- Client A retries at 100ms
- Client B retries at 150ms
- Client C retries at 120ms
- ... (staggered)

The vendor sees a smooth increase in load, not a sudden
spike.

## The "max attempts" choice

- **Too few (1-2):** You give up too easily; a transient
  error becomes a permanent failure
- **Too many (10+):** You waste time retrying a permanently
  failed request
- **Right (3-5):** You handle transient errors without
  overdoing it

For vendor APIs, 3-5 attempts is standard.

## The "retryable errors" choice

Not all errors should be retried:
- ✅ **Retry:** 429 (rate limit), 500 (server error), 502
  (bad gateway), 503 (unavailable), 504 (gateway timeout)
- ❌ **Don't retry:** 400 (bad request), 401 (unauthorized),
  403 (forbidden), 404 (not found), 422 (unprocessable)

```ts
function isRetryable(err: any): boolean {
  if (err.status === 429 || err.status === 502 || err.status === 503 || err.status === 504) {
    return true;
  }
  if (err.status >= 500 && err.status < 600) return true;
  return false;
}

async function withSmartRetry<T>(fn: () => Promise<T>): Promise<T> {
  let lastError: any;
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      return await fn();
    } catch (err: any) {
      lastError = err;
      if (!isRetryable(err)) throw err;  // Don't retry 4xx
      // ... backoff
    }
  }
  throw lastError;
}
```

## The "circuit breaker" pattern

Combine retry with a circuit breaker:
```ts
class CircuitBreaker {
  private failures = 0;
  private lastFailure = 0;
  private state: 'closed' | 'open' | 'half-open' = 'closed';

  constructor(
    private threshold = 5,
    private timeoutMs = 60_000,
  ) {}

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === 'open') {
      if (Date.now() - this.lastFailure > this.timeoutMs) {
        this.state = 'half-open';
      } else {
        throw new Error('Circuit open');
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (err) {
      this.onFailure();
      throw err;
    }
  }

  private onSuccess() {
    this.failures = 0;
    this.state = 'closed';
  }

  private onFailure() {
    this.failures++;
    this.lastFailure = Date.now();
    if (this.failures >= this.threshold) {
      this.state = 'open';
    }
  }
}
```

When the circuit is open, the request fails fast (no retry).
After a timeout, the circuit goes "half-open" — try one
request. If it succeeds, close; if it fails, open again.

## The "deadline" pattern

For long operations, use a deadline:
```ts
async function fetchWithDeadline(url: string, deadlineMs: number): Promise<Response> {
  const start = Date.now();

  return withBackoff(async () => {
    const remaining = deadlineMs - (Date.now() - start);
    if (remaining <= 0) throw new Error('Deadline exceeded');

    const controller = new AbortController();
    setTimeout(() => controller.abort(), remaining);

    return fetch(url, { signal: controller.signal });
  });
}
```

The total time is bounded by `deadlineMs`, regardless of
how many retries.

## The "CF Workers + retry" gotcha

CF Workers has a max duration (Bundled: 30s; Unbound: 5 min
for HTTP, longer for cron). If your retry takes longer than
the Worker duration, the request is killed.

For long retry chains:
- Use a queue (CF Queues) for async retries
- Use a Durable Object for stateful retry
- Use a cron to retry the failed job

## The "idempotency key" pattern

For POST/PATCH/DELETE, retries are dangerous. The first
request may have succeeded; the retry may double-charge.

**Use an idempotency key:**
```ts
async function createPayment(input: PaymentInput, env: Env): Promise<Payment> {
  const idempotencyKey = crypto.randomUUID();

  return withBackoff(async () => {
    return fetch('https://api.stripe.com/v1/charges', {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey,
        'Authorization': `Bearer ${env.STRIPE_SECRET_KEY}`,
      },
      body: JSON.stringify(input),
    });
  });
}
```

The vendor (Stripe) de-duplicates by `Idempotency-Key`. If
the request is retried, the same response is returned.

## Verification
- **Test:** `test/retry.test.ts > retries on 503, gives up
  on 400` — passes
- **Test:** `test/retry.test.ts > backoff doubles each
  attempt` — passes
- **Live:** Retry count is monitored; alerts on excessive
  retries
- **Audit:** Quarterly review of retry logic

## Gotchas
- **The "retry everything" anti-pattern.** Retrying 4xx
  errors wastes time and confuses logs.
- **The "no jitter" anti-pattern.** All clients retry at the
  same moment, making the outage worse.
- **The "retry forever" anti-pattern.** Some errors are
  permanent; retrying doesn't help.
- **The "side effects on retry" anti-pattern.** Retrying a
  POST may double-charge. Use idempotency keys.
- **The "no deadline" anti-pattern.** A retry chain that
  takes hours is a bug. Set a deadline.
- **The "retry inside retry" anti-pattern.** The vendor
  retries internally too. Your retries add to the load.
  Use circuit breakers.

## Related
- `retry-with-jitter.md` (the basic pattern)
- `circuit-breaker-pattern.md`
- `idempotency-keys.md`
- `saga-pattern.md`
- AWS: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Stripe idempotency: https://stripe.com/docs/api/idempotent_requests
