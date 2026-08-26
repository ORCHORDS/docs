# graceful-degradation-detail

**Issue:** Graceful degradation — when a dep fails
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app depends on Stripe. Stripe has an outage. Your
checkout fails. Users see errors. Revenue drops to zero.
You have no idea Stripe is down until users complain.

## Root cause
**External dependencies fail.** Your app should not fail
because Stripe is down.

**Source:** AWS — Building resilient systems:
https://aws.amazon.com/builders-library/

> "A resilient system continues to function when
> components fail."

## The 5 patterns

### 1. Circuit breaker
- **What:** Stop calling a failing service
- **When:** After N failures, open the circuit
- **Benefit:** Don't waste time on a known-failing service

```ts
class CircuitBreaker {
  private state: 'closed' | 'open' | 'half-open' = 'closed';

  async execute<T>(fn: () => Promise<T>, fallback: () => T): Promise<T> {
    if (this.state === 'open') {
      return fallback();  // Use fallback
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
}

// Usage
const breaker = new CircuitBreaker();
const result = await breaker.execute(
  () => stripe.charges.create(input),
  () => ({ status: 'queued', reason: 'payment_provider_unavailable' }),
);
```

### 2. Fallback
- **What:** Use a simpler alternative when the main fails
- **When:** The main service is down

```ts
async function getUserRecommendations(userId: string, env: Env): Promise<string[]> {
  try {
    return await env.AI.run('@cf/meta/llama-2-7b-chat-int8', { ... });
  } catch (err) {
    // Fallback: popular items
    return getPopularItems();
  }
}
```

### 3. Cached response
- **What:** Serve a cached response when the source is down
- **When:** The source fails, but we have a recent cache

```ts
async function getUserProfile(userId: string, env: Env): Promise<User | null> {
  // Try the source
  try {
    const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(userId).first<User>();
    if (user) {
      // Update cache
      await env.KV.put(`user:${userId}`, JSON.stringify(user), { expirationTtl: 300 });
      return user;
    }
  } catch (err) {
    // DB is down; use cache
    const cached = await env.KV.get(`user:${userId}`);
    if (cached) return JSON.parse(cached);
    return null;  // No data
  }
  return null;
}
```

### 4. Queue + retry
- **What:** Defer the work when the dep is down
- **When:** The dep is temporarily down; we can retry later

```ts
async function sendEmail(input: EmailInput, env: Env): Promise<void> {
  try {
    await resend.emails.send(input);
  } catch (err) {
    // Queue for retry
    await env.EMAIL_QUEUE.send({ input, retryCount: 0 });
  }
}
```

The email is sent when the vendor recovers.

### 5. Default to "safe"
- **What:** Return a safe default when the dep is down
- **When:** The user gets a working but degraded experience

```ts
async function checkFraudScore(userId: string, env: Env): Promise<'low' | 'medium' | 'high'> {
  try {
    return await env.FRAUD_API.check(userId);
  } catch (err) {
    return 'medium';  // Default to medium (cautious)
  }
}
```

The user can still transact, but with extra verification.

## The "graceful degradation" decision matrix

| Dep is down | User impact | Action |
|---|---|---|
| Payment | Can't pay | Queue + retry; show "trying" |
| Email | No email | Queue + retry; UX note |
| Search | No search | Fallback to popular items |
| Recommendations | No recs | Fallback to popular |
| AI inference | No AI | Fallback to simple algorithm |
| Auth | Can't log in | Fail (auth is critical) |
| DB | Can't load data | Cached response (if available) |

## The "what's critical" decision

Not all features can be gracefully degraded:
- **Auth:** Must work; can't fail
- **DB writes:** Must succeed (or queue)
- **Payment:** Can queue
- **Email:** Can queue
- **Search:** Can fall back

For each feature, decide:
- **Critical:** Must work; fail hard if it doesn't
- **Important:** Can queue + retry
- **Nice-to-have:** Can fall back to default

## The "user experience" pattern

For a degraded mode, tell the user:
```ts
// In the response
response.headers.set('X-Degraded', 'true');
// Or in the body
{
  "data": [...],
  "degraded": true,
  "message": "Showing cached results while we update"
}
```

The user knows the experience is degraded.

## The "feature flag" pattern

For degradation, use a feature flag:
```ts
if (await isFeatureEnabled('use-cache-fallback', ctx)) {
  return getCachedResponse();
}
return getLiveResponse();
```

You can toggle the flag to control degradation.

## The "circuit breaker" details

For a good circuit breaker:
- **Threshold:** 5 failures in 60s → open
- **Reset timeout:** 60s after open, try half-open
- **Half-open:** Try 1 request; if it succeeds, close; if
  it fails, open again

```ts
class CircuitBreaker {
  private failures = 0;
  private state: 'closed' | 'open' | 'half-open' = 'closed';
  private lastFailure = 0;

  constructor(
    private threshold = 5,
    private timeoutMs = 60_000,
  ) {}

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
    if (this.failures >= this.threshold) {
      this.state = 'open';
    }
  }
}
```

## The "bulkhead" pattern

For isolation, use bulkheads (separate pools per dep):
```ts
class Bulkheads {
  private pools = new Map<string, Semaphore>();

  getPool(dep: string): Semaphore {
    if (!this.pools.has(dep)) {
      this.pools.set(dep, new Semaphore(10));  // Max 10 concurrent
    }
    return this.pools.get(dep)!;
  }
}

// Usage
const pool = bulkheads.getPool('stripe');
await pool.acquire();
try {
  return await stripe.charges.create(input);
} finally {
  pool.release();
}
```

If Stripe is slow, it doesn't block other deps.

## The "timeout" pattern

For every external call, set a timeout:
```ts
async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), timeoutMs);

  return fetch(url, { signal: controller.signal });
}

try {
  return await fetchWithTimeout('https://api.stripe.com/...', 5000);
} catch (err) {
  if (err.name === 'AbortError') {
    return fallback();
  }
  throw err;
}
```

The timeout prevents waiting forever.

## The "dependency inventory" pattern

Document every external dep:
```markdown
## External dependencies

| Dep | Critical | Timeout | Fallback |
|---|---|---|---|
| Stripe | Yes | 5s | Queue + retry |
| Resend (email) | No | 10s | Queue + retry |
| OpenAI | No | 30s | Static response |
| Fraud API | Yes | 3s | Default to medium |
| Algolia | No | 5s | DB fallback |
| Slack | No | 5s | Skip |
```

For each dep, document the timeout + fallback.

## The "test the degradation" pattern

Test the app when deps are down:
```ts
test('checkout works when Stripe is down', async () => {
  // Mock Stripe to throw
  vi.mocked(stripe.charges.create).mockRejectedValue(new Error('Stripe down'));

  const response = await checkout(input);
  expect(response.status).toBe(202);
  expect(response.body).toEqual({ status: 'queued' });
});
```

The test verifies the fallback works.

## The "monitor the degradation" pattern

Track how often fallbacks are used:
```ts
metrics.increment('stripe.fallback_total', { reason: 'circuit_open' });
metrics.increment('stripe.fallback_total', { reason: 'timeout' });
metrics.increment('stripe.fallback_total', { reason: 'error' });
```

The metrics show when degradation is happening.

## The "post-mortem" pattern

After a dep outage:
1. **How long was it down?**
2. **What was the user impact?**
3. **Did the fallback work?**
4. **What can we improve?**

Document the answers; share with the team.

## Verification
- **Test:** Fallback works when dep is down
- **Live:** Fallback metrics are monitored
- **Audit:** Quarterly dep review

## Gotchas
- **The "fallback is the same as the main" anti-pattern.**
  If both fail, you have no protection. Test the fallback
  in isolation.
- **The "no timeout" anti-pattern.** A request that waits
  forever is a bug. Always set a timeout.
- **The "circuit breaker never closes" anti-pattern.** A
  bug in the breaker can keep it open forever. Test the
  close logic.
- **The "silent fallback" anti-pattern.** A fallback that
  silently gives wrong results is a bug. Log + alert.
- **The "every dep has the same timeout" anti-pattern.**
  Each dep should have its own timeout based on its
  SLA.

## Related
- `circuit-breaker-pattern.md`
- `retry-with-exponential-backoff.md`
- `cache-strategies.md`
- `caching-strategies-detail.md`
- `feature-flags.md`
- AWS: https://aws.amazon.com/builders-library/
- Hystrix: https://github.com/Netflix/Hystrix
