# feature-cookbook-error-recovery

**Issue:** Error recovery — retries, fallbacks, compensation
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app calls a vendor API. The vendor is slow. The
request times out. The user sees an error. You retry.
The vendor is still slow. You retry again. The vendor
is down. The user is angry.

## Root cause
**Errors are inevitable.** Without a recovery strategy,
they cascade.

**Source:** AWS — Building resilient systems.

## The "retry" pattern

For transient errors, retry:
```ts
async function withRetry<T>(fn: () => Promise<T>, maxAttempts = 3): Promise<T> {
  let lastError: Error | undefined;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err as Error;
      if (attempt === maxAttempts - 1) break;
      if (!isRetryable(err)) throw err;
      await sleep(Math.min(1000 * 2 ** attempt, 30_000));
    }
  }

  throw lastError!;
}
```

The retry is exponential; transient errors recover.

## The "exponential backoff" pattern

For the retry delay:
```ts
function backoff(attempt: number, baseMs = 1000, maxMs = 30_000): number {
  return Math.min(baseMs * 2 ** attempt, maxMs);
}

// + jitter
function backoffWithJitter(attempt: number): number {
  const exp = backoff(attempt);
  return exp + Math.random() * exp * 0.5;  // 0-50% jitter
}
```

Jitter prevents the thundering herd.

## The "circuit breaker" pattern

For a failing dep, stop calling it:
```ts
class CircuitBreaker {
  private failures = 0;
  private state: 'closed' | 'open' | 'half-open' = 'closed';
  private lastFailure = 0;

  constructor(private threshold = 5, private timeoutMs = 60_000) {}

  async execute<T>(fn: () => Promise<T>, fallback: () => T): Promise<T> {
    if (this.state === 'open') {
      if (Date.now() - this.lastFailure > this.timeoutMs) {
        this.state = 'half-open';
      } else {
        return fallback();
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (err) {
      this.onFailure();
      return fallback();
    }
  }

  private onSuccess() {
    this.failures = 0;
    this.state = 'closed';
  }

  private onFailure() {
    this.failures++;
    this.lastFailure = Date.now();
    if (this.failures >= this.threshold) this.state = 'open';
  }
}
```

The breaker stops calling the failing dep.

## The "fallback" pattern

For a failing dep, use a fallback:
```ts
async function getRecommendations(userId: string, env: Env): Promise<any[]> {
  try {
    return await env.AI.run('@cf/meta/llama-2-7b-chat-int8', { ... });
  } catch (err) {
    logEvent('ai.recommendation.failed', 'warn', { userId, error: String(err) });
    return getPopularItems();  // Fallback
  }
}
```

The user gets something, not nothing.

## The "queue" pattern

For async recovery, queue:
```ts
async function sendEmail(input: EmailInput, env: Env): Promise<void> {
  try {
    await resend.emails.send(input);
  } catch (err) {
    // Queue for later retry
    await env.EMAIL_QUEUE.send(input);
  }
}
```

The email is sent when the vendor recovers.

## The "DLQ" pattern

For permanently failed jobs, DLQ:
```ts
async function processWithDLQ(job: Job, env: Env, maxAttempts = 5): Promise<void> {
  const attempts = await getAttempts(job.id, env);

  try {
    await doWork(job, env);
    await env.KV.delete(`attempts:${job.id}`);
  } catch (err) {
    if (attempts >= maxAttempts - 1) {
      await env.DLQ.send({ ...job, error: String(err), failedAt: new Date().toISOString() });
      return;
    }
    await env.KV.put(`attempts:${job.id}`, String(attempts + 1));
    throw err;  // Trigger retry
  }
}
```

Failed jobs go to a DLQ for inspection.

## The "idempotency" pattern

For retried jobs, idempotency:
```ts
async function processPayment(paymentId: string, env: Env): Promise<void> {
  const processed = await env.KV.get(`processed:${paymentId}`);
  if (processed) return;

  await chargeUser(paymentId, env);
  await env.KV.put(`processed:${paymentId}`, '1', { expirationTtl: 86400 * 30 });
}
```

The payment is processed once, even on retry.

## The "compensation" pattern

For a multi-step operation, compensate on failure:
```ts
async function placeOrderSaga(order: Order, env: Env): Promise<void> {
  const compensations: Array<() => Promise<void>> = [];

  try {
    // Step 1: Charge
    const charge = await chargeUser(order, env);
    compensations.push(() => refundUser(charge.id, env));

    // Step 2: Reserve inventory
    const reservation = await reserveInventory(order, env);
    compensations.push(() => releaseInventory(reservation.id, env));

    // Step 3: Create shipment
    await createShipment(order, env);
  } catch (err) {
    // Compensate in reverse order
    for (const compensation of compensations.reverse()) {
      try {
        await compensation();
      } catch (compensationErr) {
        logEvent('compensation.failed', 'error', { error: String(compensationErr) });
      }
    }
    throw err;
  }
}
```

The saga compensates on failure.

## The "fail open" pattern

For a non-critical dep, fail open:
```ts
try {
  const { allowed } = await checkRateLimit(userId, env);
  if (!allowed) return new Response('Rate limited', { status: 429 });
} catch (err) {
  // Rate limiter is down; allow the request
  console.error({ msg: 'rate.limit.error', error: String(err) });
}

return next();
```

Failing open is safer than failing closed (which blocks
all users).

## The "fail closed" pattern

For a critical dep (auth, payment), fail closed:
```ts
try {
  const user = await authenticate(request, env);
  if (!user) return new Response('Unauthorized', { status: 401 });
} catch (err) {
  // Auth is down; deny
  console.error({ msg: 'auth.error', error: String(err) });
  return new Response('Service unavailable', { status: 503 });
}
```

A wrong payment is worse than a failed payment.

## The "graceful degradation" pattern

For a degraded experience:
```ts
async function getDashboard(userId: string, env: Env): Promise<Dashboard> {
  const [user, posts, recommendations] = await Promise.allSettled([
    getUser(userId, env),
    getRecentPosts(userId, env),
    getRecommendations(userId, env),  // May fail
  ]);

  return {
    user: user.status === 'fulfilled' ? user.value : null,
    posts: posts.status === 'fulfilled' ? posts.value : [],
    recommendations: recommendations.status === 'fulfilled' ? recommendations.value : getPopularItems(),
  };
}
```

The dashboard works even if some parts fail.

## The "user-friendly error" pattern

For a user-friendly error:
```ts
function userMessage(err: Error): string {
  if (err instanceof ValidationError) return 'Please check the form and try again.';
  if (err instanceof NotFoundError) return 'The item was not found.';
  if (err instanceof UnauthorizedError) return 'Please sign in to continue.';
  if (err instanceof ForbiddenError) return 'You do not have permission to do this.';
  if (err.message.includes('timeout')) return 'The service is busy. Please try again in a moment.';
  return 'Something went wrong. Please try again later.';
}
```

The user gets a clear, actionable message.

## The "error log" pattern

For an error log:
```ts
logEvent('error', 'error', {
  error: err.message,
  stack: err.stack,
  userId: ctx.user?.id,
  requestId: ctx.requestId,
  url: request.url,
});
```

The log has full context for debugging.

## Verification
- **Test:** Retry works on transient errors
- **Test:** Circuit breaker opens + closes
- **Test:** Fallback is used
- **Test:** DLQ captures failed jobs
- **Live:** Error rate is monitored
- **Audit:** Quarterly error review

## Gotchas
- **The "no retry" anti-pattern.** Transient errors are
  recoverable.
- **The "retry forever" anti-pattern.** Set a max
  attempt count.
- **The "fail closed for non-critical" anti-pattern.**
  Block all users = disaster.
- **The "no idempotency" anti-pattern.** Retries do the
  work twice.
- **The "no compensation" anti-pattern.** A failed step
  leaves the system inconsistent.

## Related
- `error-handling-strategies.md`
- `error-codes-and-messages.md`
- `retry-with-exponential-backoff.md`
- `circuit-breaker-pattern.md`
- `graceful-degradation-detail.md`
- `feature-resilience-patterns.md`
- `saga-pattern.md`
- `idempotency-keys.md`
- `cloudflare/workers-workers-queues-patterns.md`
