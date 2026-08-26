# feature-resilience-patterns

**Issue:** Resilience patterns — bulkhead, timeout, retry, fallback
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app calls a slow vendor API. The request takes 30s.
The Worker times out. The user sees an error. The other
endpoints are still fast. The slow vendor blocks the
Worker.

## Root cause
**A slow dep can take down your whole app.** Use resilience
patterns.

**Source:** AWS — Building resilient systems:
https://aws.amazon.com/builders-library/

## The 6 resilience patterns

### 1. Timeout
- **What:** Set a max time for every external call
- **Why:** A call that waits forever is a bug

```ts
async function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Timeout')), timeoutMs)
    ),
  ]);
}

const result = await withTimeout(stripe.charges.create(input), 5000);
```

### 2. Retry
- **What:** Retry on transient failures
- **Why:** A 5xx is usually transient; retry

```ts
async function withRetry<T>(fn: () => Promise<T>, options?: { maxAttempts?: number }): Promise<T> {
  const maxAttempts = options?.maxAttempts ?? 3;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt === maxAttempts - 1) throw err;
      if (!isRetryable(err)) throw err;
      await sleep(Math.min(100 * 2 ** attempt, 30_000));
    }
  }
  throw new Error('Unreachable');
}
```

### 3. Circuit breaker
- **What:** Stop calling a failing service
- **Why:** A failing service slows you down; let it recover

```ts
class CircuitBreaker {
  // ... see circuit-breaker-pattern.md
}
```

### 4. Bulkhead
- **What:** Isolate resources per dep
- **Why:** One dep's failure doesn't block others

```ts
class Bulkhead {
  private semaphores = new Map<string, Semaphore>();

  async execute<T>(key: string, fn: () => Promise<T>, maxConcurrent = 10): Promise<T> {
    if (!this.semaphores.has(key)) {
      this.semaphores.set(key, new Semaphore(maxConcurrent));
    }
    const sem = this.semaphores.get(key)!;
    await sem.acquire();
    try {
      return await fn();
    } finally {
      sem.release();
    }
  }
}
```

### 5. Fallback
- **What:** Use a simpler alternative when the main fails
- **Why:** The user gets something, not nothing

```ts
async function getRecommendations(userId: string, env: Env): Promise<string[]> {
  try {
    return await env.AI.run(...);
  } catch (err) {
    return getPopularItems();  // Fallback
  }
}
```

### 6. Rate limit
- **What:** Limit requests per user / per IP
- **Why:** A misbehaving client doesn't take down the service

```ts
// See api-rate-limiting-detail.md
```

## The "composite" pattern

Combine the patterns:
```ts
class ResilientClient {
  private breaker = new CircuitBreaker();
  private bulkhead = new Bulkhead();

  async call<T>(key: string, fn: () => Promise<T>, fallback: () => T): Promise<T> {
    return this.bulkhead.execute(key, () =>
      this.breaker.execute(() =>
        withTimeout(withRetry(fn), 5000),
        fallback
      )
    );
  }
}

// Usage
const result = await client.call('stripe', () => stripe.charges.create(input), () => ({ status: 'queued' }));
```

The client is resilient: timeout, retry, breaker, bulkhead,
fallback.

## The "chaos engineering" pattern

For testing resilience, inject failures:
```ts
// Simulate a slow vendor
async function slowStripe(): Promise<any> {
  await sleep(10_000);  // 10s delay
  return stripe.charges.create(input);
}

// Test the resilience
const result = await client.call('stripe', slowStripe, () => ({ status: 'queued' }));
// The timeout kicks in at 5s; the fallback returns immediately
```

Use **chaos engineering** tools (Gremlin, Chaos Monkey) for
production.

## The "rate limit" pattern

For per-user rate limiting, use a DO:
```ts
class RateLimiter implements DurableObject {
  // ... see api-rate-limiting-detail.md
}
```

## The "monitoring" pattern

For resilience metrics:
```ts
metrics.increment('resilience.retry_total', { dep: 'stripe' });
metrics.increment('resilience.circuit_open_total', { dep: 'stripe' });
metrics.increment('resilience.fallback_total', { dep: 'stripe' });
metrics.histogram('resilience.duration_ms', duration, { dep: 'stripe', outcome: 'success' });
```

The metrics show when resilience is kicking in.

## The "alerting" pattern

Alert when:
- **Circuit is open** (a dep is failing)
- **Fallback is used heavily** (a dep is degraded)
- **Retry count is high** (transient failures)

```ts
if (circuitBreakerState === 'open') {
  pageOncall('Circuit open', { dep: 'stripe' });
}
```

## The "fail open vs fail closed" decision

For each dep:
- **Fail open:** The request succeeds with a fallback
  (less user impact)
- **Fail closed:** The request fails
  (correctness)

For most apps, **fail open** is the right answer. The user
gets something (cached, fallback) instead of nothing.

For critical apps (payments, auth), **fail closed** may be
right. A wrong payment is worse than a failed payment.

## The "backpressure" pattern

For overloaded services, apply backpressure:
```ts
class Backpressure {
  private inflight = 0;
  private maxInflight = 100;

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    while (this.inflight >= this.maxInflight) {
      await sleep(10);
    }
    this.inflight++;
    try {
      return await fn();
    } finally {
      this.inflight--;
    }
  }
}
```

When the service is overloaded, the queue grows. The
caller waits.

## The "shed load" pattern

For overload, drop non-critical work:
```ts
function shouldShedLoad(request: Request): boolean {
  // Shed if the queue is too long
  return queueDepth > 1000 && !isCriticalRequest(request);
}

if (shouldShedLoad(request)) {
  return new Response('Service busy', { status: 503 });
}
```

The user gets a fast 503; the critical requests are
processed.

## The "graceful shutdown" pattern

For shutdown, finish in-flight work:
```ts
let isShuttingDown = false;

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (isShuttingDown) {
      return new Response('Server shutting down', { status: 503 });
    }
    return handleRequest(request, env, ctx);
  },
};

// On SIGTERM
process.on('SIGTERM', async () => {
  isShuttingDown = true;
  await waitForInFlightRequests();
  process.exit(0);
});
```

CF handles this automatically (the Worker is killed after
the response).

## Verification
- **Test:** Timeout works
- **Test:** Retry works on transient failures
- **Test:** Circuit breaker opens + closes
- **Test:** Fallback is used when main fails
- **Live:** Resilience metrics are monitored
- **Chaos test:** Periodic chaos engineering

## Gotchas
- **The "no timeout" anti-pattern.** A call that waits
  forever is a bug. Always set a timeout.
- **The "no retry budget" anti-pattern.** Retrying forever
  is a bug. Set a max retry count.
- **The "circuit breaker never closes" anti-pattern.**
  Test the close logic.
- **The "fallback that lies" anti-pattern.** A fallback
  that returns wrong data is worse than no fallback.
- **The "no chaos testing" anti-pattern.** Resilience
  patterns that work in tests may fail in production.
  Test with real failures.

## Related
- `circuit-breaker-pattern.md`
- `retry-with-exponential-backoff.md`
- `graceful-degradation-detail.md`
- `api-rate-limiting-detail.md`
- `observability-three-pillars-detail.md`
- AWS: https://aws.amazon.com/builders-library/
- Hystrix: https://github.com/Netflix/Hystrix
- Gremlin: https://www.gremlin.com/
