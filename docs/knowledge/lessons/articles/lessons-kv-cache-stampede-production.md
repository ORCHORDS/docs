# KV Cache Stampede Production Incident: 50× Origin Traffic Spike on Key Expiry

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

At 02:17 UTC the product-pricing API returned 503s for approximately 90 seconds. APM traces showed origin database CPU spiking to 100% simultaneously with a sharp drop in KV cache hit rate. The origin had previously been serving around 200 req/s through KV caching; at the moment the pricing KV key expired, origin load jumped to 10,400 req/s — roughly 50× normal — as all globally distributed Worker instances simultaneously discovered the cache was empty and forwarded to the database.

---

## Context

Cloudflare KV is an eventually-consistent edge key-value store. When a key's TTL expires, every Worker instance in every PoP that holds an in-flight request finds the key missing and falls back to the origin simultaneously. This is the classic thundering-herd / cache-stampede problem. Our pricing cache key had a 60-second TTL with no jitter and no background refresh. Weeknight batch cron jobs invalidated thousands of pricing keys at the same time (all set with the same TTL from the same cron run), creating coordinated simultaneous expiry across the global edge.

---

## Root Cause: Simultaneous Key Expiry Across All Edge Nodes

The original caching pattern had no mechanism to stagger refreshes or prevent concurrent origin requests:

```typescript
// BEFORE — stampede-prone: all misses hit origin simultaneously
export async function getProductPricing(
  kv: KVNamespace,
  productId: string,
  origin: OriginClient
): Promise<PricingData> {
  const cacheKey = `pricing:${productId}`;

  // Every Worker instance checks KV at the same time.
  // When TTL expires, all instances miss simultaneously.
  const cached = await kv.get<PricingData>(cacheKey, 'json');
  if (cached) return cached;

  // All instances race to call the origin at the same millisecond
  const fresh = await origin.fetchPricing(productId);

  // All instances write back — N redundant writes
  await kv.put(cacheKey, JSON.stringify(fresh), { expirationTtl: 60 });

  return fresh;
}
```

The batch cron that refreshed prices:

```typescript
// BEFORE — all keys get the same TTL, expire at the same wall-clock second
async function refreshAllPricing(kv: KVNamespace, db: D1Database): Promise<void> {
  const products = await db.prepare('SELECT id FROM products').all<{ id: string }>();
  for (const { id } of products.results) {
    const pricing = await fetchPricingFromExternalApi(id);
    // All set with expirationTtl: 60 → expire at cron_start + 60s simultaneously
    await kv.put(`pricing:${id}`, JSON.stringify(pricing), { expirationTtl: 60 });
  }
}
```

---

## Fix: Probabilistic Early Revalidation + Durable Object Single-Flight Lock

### Strategy A — Probabilistic Early Revalidation (XFetch algorithm)

The XFetch algorithm revalidates a cache entry probabilistically before it expires. As the key approaches its TTL, each Worker independently decides whether to revalidate based on a random draw weighted by how close to expiry the key is. This spreads refreshes across many Workers over time, preventing the synchronised miss:

```typescript
interface CachedValue<T> {
  data: T;
  fetchedAt: number; // Unix timestamp ms
  ttlMs: number;     // Total TTL in milliseconds
}

/**
 * Probabilistic early revalidation (XFetch / "optimal probabilistic cache
 * stampede prevention", Vattani et al. 2015).
 *
 * A Worker revalidates early with probability:
 *   P(revalidate) = age/ttl raised to the power `beta` (default 4).
 * Higher beta = more conservative (revalidates later, closer to expiry).
 */
function shouldEarlyRevalidate(
  fetchedAt: number,
  ttlMs: number,
  beta = 4
): boolean {
  const age = Date.now() - fetchedAt;
  if (age < 0) return false;
  const ratio = age / ttlMs;
  return Math.random() < ratio ** beta;
}

export async function getPricingWithXFetch(
  kv: KVNamespace,
  productId: string,
  origin: OriginClient
): Promise<PricingData> {
  const cacheKey = `pricing:${productId}`;
  const TTL_MS = 60_000;

  const stored = await kv.get<CachedValue<PricingData>>(cacheKey, 'json');

  // Serve stale data while triggering background refresh
  if (stored && !shouldEarlyRevalidate(stored.fetchedAt, stored.ttlMs)) {
    return stored.data;
  }

  // Either a true cache miss or we won the early-revalidation lottery
  const fresh = await origin.fetchPricing(productId);
  const envelope: CachedValue<PricingData> = {
    data: fresh,
    fetchedAt: Date.now(),
    ttlMs: TTL_MS,
  };

  // Write with extra TTL buffer — the envelope's fetchedAt drives logical expiry
  await kv.put(cacheKey, JSON.stringify(envelope), {
    expirationTtl: Math.ceil((TTL_MS * 1.5) / 1000), // keep in KV 50% longer than logical TTL
  });

  return fresh;
}

// Cron: add per-key jitter to stagger expiry across the batch
async function refreshAllPricingWithJitter(
  kv: KVNamespace,
  db: D1Database
): Promise<void> {
  const products = await db.prepare('SELECT id FROM products').all<{ id: string }>();
  for (const { id } of products.results) {
    const pricing = await fetchPricingFromExternalApi(id);
    // Jitter: ±15 s around a 60 s base TTL
    const jitterSec = Math.floor(Math.random() * 30) - 15;
    const ttlSec = 60 + jitterSec;
    const envelope: CachedValue<PricingData> = {
      data: pricing,
      fetchedAt: Date.now(),
      ttlMs: ttlSec * 1000,
    };
    await kv.put(`pricing:${id}`, JSON.stringify(envelope), {
      expirationTtl: Math.ceil(ttlSec * 1.5),
    });
  }
}
```

### Strategy B — Durable Object Single-Flight Lock

For high-traffic keys where even probabilistic revalidation may produce too many concurrent origin calls, use a Durable Object as a serialising lock. Only one DO instance refreshes the cache; all other Workers receive a promise that resolves when the refresh completes:

```typescript
// PricingRefreshDO — ensures single-flight origin fetch per product
export class PricingRefreshDO implements DurableObject {
  private refreshPromise: Promise<PricingData> | null = null;

  constructor(
    private readonly state: DurableObjectState,
    private readonly env: Env
  ) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const productId = url.searchParams.get('productId');
    if (!productId) return new Response('missing productId', { status: 400 });

    // If a refresh is already in flight, await it instead of issuing a second origin request
    if (!this.refreshPromise) {
      this.refreshPromise = this.doRefresh(productId).finally(() => {
        this.refreshPromise = null;
      });
    }

    const data = await this.refreshPromise;
    return new Response(JSON.stringify(data), {
      headers: { 'Content-Type': 'application/json' },
    });
  }

  private async doRefresh(productId: string): Promise<PricingData> {
    const fresh = await fetch(
      `https://pricing-origin.internal/products/${productId}/price`
    ).then((r) => r.json() as Promise<PricingData>);

    // Write result to KV so subsequent edge Workers can serve it without hitting the DO
    const envelope: CachedValue<PricingData> = {
      data: fresh,
      fetchedAt: Date.now(),
      ttlMs: 60_000,
    };
    await this.env.PRICING_KV.put(
      `pricing:${productId}`,
      JSON.stringify(envelope),
      { expirationTtl: 90 }
    );

    return fresh;
  }
}

// Worker fetch handler: KV first, DO on miss
export async function getPricingWithDOLock(
  kv: KVNamespace,
  env: Env,
  productId: string
): Promise<PricingData> {
  const cacheKey = `pricing:${productId}`;
  const stored = await kv.get<CachedValue<PricingData>>(cacheKey, 'json');

  if (stored && !shouldEarlyRevalidate(stored.fetchedAt, stored.ttlMs)) {
    return stored.data;
  }

  // Route to the DO — only one instance of the DO will hit origin
  const doId = env.PRICING_REFRESH_DO.idFromName(productId);
  const stub = env.PRICING_REFRESH_DO.get(doId);
  const response = await stub.fetch(
    `https://do-internal/refresh?productId=${productId}`
  );
  return response.json() as Promise<PricingData>;
}
```

---

## Monitoring / Detection

```typescript
export async function getPricingInstrumented(
  kv: KVNamespace,
  productId: string,
  origin: OriginClient,
  env: Env
): Promise<PricingData> {
  const cacheKey = `pricing:${productId}`;
  const stored = await kv.get<CachedValue<PricingData>>(cacheKey, 'json');

  const isHit = !!stored && !shouldEarlyRevalidate(stored.fetchedAt, stored.ttlMs);

  env.ANALYTICS.writeDataPoint({
    blobs: ['kv_pricing', isHit ? 'hit' : 'miss'],
    doubles: [1],
    indexes: ['cache_outcome'],
  });

  if (!isHit) {
    const fresh = await origin.fetchPricing(productId);
    const envelope: CachedValue<PricingData> = {
      data: fresh,
      fetchedAt: Date.now(),
      ttlMs: 60_000,
    };
    await kv.put(cacheKey, JSON.stringify(envelope), { expirationTtl: 90 });
    return fresh;
  }

  return stored!.data;
}

// Alert rule: cache hit rate dropping below 90% triggers a PagerDuty alert
// Analytics Engine query (run from a Cron Trigger):
//   SELECT
//     SUM(CASE WHEN blob2='hit' THEN double1 ELSE 0 END) /
//     SUM(double1) AS hit_rate
//   FROM DATASET
//   WHERE timestamp > NOW() - INTERVAL '5' MINUTE
```

---

## Anti-patterns

- **Uniform TTL across a batch of keys written at the same time** — Always add per-key jitter (±10–30% of base TTL) to spread expiry across a time window.
- **Hard cache invalidation without a warming step** — Deleting all cache keys before writing new values creates a gap where every request misses simultaneously.
- **Serving only fresh data (no stale-while-revalidate)** — Returning stale data for a fraction of a second while revalidating in the background dramatically reduces origin load.
- **Using KV alone for single high-traffic keys without a lock** — A single key with 10,000 req/s can generate thousands of simultaneous origin calls. Use a Durable Object lock for such keys.

---

## Gotchas

- KV `expirationTtl` must be at least 60 seconds — setting it lower is rejected with an error. For sub-60s TTLs store a logical expiry timestamp in the value and check it in the Worker.
- Durable Object IDs created via `idFromName` are deterministic — the same name always resolves to the same DO globally, which is exactly what you want for a global lock.
- The XFetch beta parameter is not a standard KV concept; document it clearly in your codebase. Beta=4 means revalidation probability exceeds 50% only when the key is 84% through its TTL.
- KV read-after-write is eventually consistent. After `kv.put()` in the DO, edge Workers may still read stale values for up to 60 s from their regional cache. This is acceptable for pricing data but must be documented.
- The DO hibernates when idle. On wake, `refreshPromise` is `null` (heap is fresh), so the first request after hibernation will always hit origin — design accordingly.

---

## Verification

```bash
# Check current KV cache hit rate
npx wrangler analytics-engine query \
  --dataset cache_outcome \
  --query "
    SELECT
      blob2 as outcome,
      SUM(double1) as requests
    FROM DATASET
    WHERE timestamp > NOW() - INTERVAL '10' MINUTE
    GROUP BY blob2
  "

# Simulate a stampede locally: expire a key and send 100 concurrent requests
npx wrangler kv key delete pricing:test-product-001 --namespace-id=<KV_ID> --remote
apache2-utils ab -n 100 -c 100 https://your-worker.example.com/pricing/test-product-001

# Verify only 1-2 origin requests were made (check origin access logs)

# Test jitter distribution for cron-set keys
node -e "
const ttls = Array.from({length: 100}, () => 60 + Math.floor(Math.random()*30) - 15);
const min = Math.min(...ttls), max = Math.max(...ttls);
console.log('TTL range:', min, '-', max, 'seconds');
"
```

---

## Related

- `lessons-d1-eventual-consistency-production-incident.md`
- `lessons-durable-objects-websocket-hibernation-lost-state.md`

---

## Sources

- XFetch Algorithm — Vattani, A. et al., "Hurrying to be there when things expire" — https://cseweb.ucsd.edu/~avattani/papers/cache_stampede.pdf
- Cloudflare KV Limits — https://developers.cloudflare.com/kv/platform/limits/
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
