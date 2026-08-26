# graceful-degradation

**Issue:** When a dependency is down, the app should still work (mostly)
**Date:** 2026-08-09
**Status:** documented

## Symptom
A vendor (Stripe, SendGrid, OpenAI) has an outage. Your app
shows "Something went wrong" to all users. The vendor recovers.
Your app recovers. But for 30 minutes, no one could use your
app — even features that don't depend on the vendor.

## Root cause
**A single failure point takes down the whole app.** The
feature that calls the vendor is on the critical path for the
user, but the user can still use other features that don't
need the vendor.

**Source:** Microsoft — Design Patterns: Circuit Breaker:
https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker

## Fix
Three patterns, in order of preference:

### 1. Cached fallback
For data that doesn't change often, cache the vendor's
response and serve the cached version when the vendor is down.

```ts
async function getExchangeRates(env: Env): Promise<ExchangeRates> {
  // Try the vendor
  try {
    const rates = await fetchVendorRates();
    // Cache for 1 hour
    await env.KV.put('exchange-rates', JSON.stringify(rates), { expirationTtl: 3600 });
    return rates;
  } catch (err) {
    // Vendor is down; use cached
    const cached = await env.KV.get('exchange-rates', 'json');
    if (cached) return cached as ExchangeRates;
    throw err;  // No cache; can't serve
  }
}
```

The user sees slightly stale rates, but the app works.

### 2. Default value
For features where the vendor's data is "nice to have," use a
sensible default when the vendor is down.

```ts
async function getRecommendation(userId: string, env: Env): Promise<Post[]> {
  try {
    return await mlService.recommend(userId);
  } catch (err) {
    // ML service down; show popular posts
    return await env.DB!.prepare(
      `SELECT * FROM posts ORDER BY created_at DESC LIMIT 20`
    ).all<Post[]>().then(r => r.results);
  }
}
```

The user sees "Popular posts" instead of "Personalized for
you." The app still works.

### 3. Feature disable
For features that absolutely require the vendor, disable the
feature with a clear message.

```tsx
{await isFeatureAvailable('payment') ? (
  <CheckoutButton />
) : (
  <div className="text-gray-500">
    Checkout is temporarily unavailable. Please try again later.
  </div>
)}
```

The user knows what's happening. They can use other features.

## Per-dependency fallback strategy

| Dependency | Fallback |
|---|---|
| Stripe (payments) | Feature disable with message |
| SendGrid (email) | Queue the email; send when vendor recovers |
| OpenAI (content) | Default recommendation (popular content) |
| Cloudflare D1 | Cache read (KV); fail write with 503 |
| Cloudflare KV | Use D1 as a (slower) fallback |
| Vendor API (general) | Cached response or default value |

## Implementation

### The wrapper function
```ts
async function withGracefulDegradation<T>(
  vendor: () => Promise<T>,
  fallback: () => Promise<T>,
  options: { circuitBreaker?: CircuitBreaker } = {}
): Promise<T> {
  if (options.circuitBreaker?.state === 'open') {
    return fallback();
  }
  try {
    return await vendor();
  } catch (err) {
    // Log the failure
    console.error('vendor_failure', { err: String(err) });
    return fallback();
  }
}
```

### The feature flag
For features that should be disabled when the vendor is down,
expose the availability:
```ts
async function isFeatureAvailable(feature: string, env: Env): Promise<boolean> {
  const cached = await env.KV.get(`feature-avail:${feature}`, 'json') as { available: boolean; checkedAt: number } | null;
  if (cached && Date.now() - cached.checkedAt < 60000) {
    return cached.available;
  }
  // Check the vendor (lightweight)
  const available = await pingVendor(env);
  await env.KV.put(`feature-avail:${feature}`, JSON.stringify({ available, checkedAt: Date.now() }), { expirationTtl: 120 });
  return available;
}
```

## Verification
- **Test:** `test/graceful-degradation.test.ts > vendor down
  triggers fallback` — passes
- **Test:** `test/graceful-degradation.test.ts > vendor recovers,
  primary path is restored` — passes
- **Live:** Scheduled chaos test (kill a vendor, verify the
  app still works)

## Gotchas
- **The fallback should be visible to the user.** A silent
  fallback confuses the user. "Showing popular posts because
  the recommender is down" is better than "Showing popular
  posts" (without explanation).
- **Don't cache error responses.** If the vendor returns an
  error, don't cache it. Caching a failure means a long
  recovery time.
- **The circuit breaker is a separate concern.** See
  `circuit-breaker-pattern.md`. Use a circuit breaker to
  short-circuit the vendor call when it's known-down, instead
  of waiting for each call to fail.
- **The fallback must be tested.** A fallback that's never
  tested is a fallback that doesn't work. Schedule regular
  chaos tests.
- **Stale data is better than no data** (usually). The user
  can see the timestamp and know it's stale.

## Related
- `circuit-breaker-pattern.md`
- `retry-with-jitter.md`
- `feature-flags.md`
- Microsoft: https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker
