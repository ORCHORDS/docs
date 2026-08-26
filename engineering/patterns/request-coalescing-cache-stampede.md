# Request Coalescing and Cache Stampede Prevention

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

A cached value expires at 03:47:00. In the next 50 ms, 800 concurrent requests
arrive for that key. Every single Worker invocation reads "cache miss", fetches
the origin independently, and writes the result back to KV or the Cache API.
The origin absorbs 800× the normal load — and the problem repeats on every TTL
expiry. This is the **cache stampede** (also called thundering herd or dog-pile
effect).

The same scenario occurs when an expensive D1 aggregation query is shared across
many request paths and the result has not yet been materialized.

---

## Context

Two complementary techniques prevent cache stampedes in Cloudflare Workers:

1. **Request coalescing**: Route all inflight requests for the same cache key
   through a single **Durable Object**. The DO fetches the origin once and
   broadcasts the result to all waiting callers.

2. **Stale-while-revalidate (SWR)**: Serve the stale cached value immediately
   while a background revalidation refreshes the cache. The client never waits
   for origin; the next request after the refresh already sees fresh data.

Both patterns eliminate the window in which many concurrent Workers race to
populate a missing or expired cache entry. They are complementary: SWR reduces
stampede frequency; coalescing eliminates the stampede burst when it does occur.

---

## Pattern 1: Coalescing via Durable Objects

A Durable Object is a single-threaded actor with a globally consistent instance
per key. All Worker invocations for product `prod_123` are routed to the same DO
instance. The DO serializes the origin fetch: the first caller fetches; all
subsequent callers await the same in-flight promise.

```typescript
// src/objects/CachingDO.ts

export class CachingDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  // In-memory map: cache key → in-flight fetch promise
  private inflight = new Map<string, Promise<string>>();

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const cacheKey = url.pathname; // e.g. "/products/prod_123"

    // 1. Check DO storage (acts as a fast L1 cache inside the DO)
    const cached = await this.state.storage.get<CacheEntry>(cacheKey);
    if (cached && cached.expiresAt > Date.now()) {
      return Response.json(cached.data, {
        headers: { 'X-Cache': 'HIT', 'X-Cache-Age': String(Date.now() - cached.cachedAt) },
      });
    }

    // 2. Stale-while-revalidate: serve stale immediately, refresh in background
    if (cached && cached.staleUntil > Date.now()) {
      // Serve stale, trigger background refresh if not already inflight
      if (!this.inflight.has(cacheKey)) {
        this.inflight.set(cacheKey, this.doFetch(cacheKey).finally(() => {
          this.inflight.delete(cacheKey);
        }));
        // Note: background promise is not awaited — serves as a "fire and update"
      }
      return Response.json(cached.data, {
        headers: { 'X-Cache': 'STALE' },
      });
    }

    // 3. Cache miss or fully expired: coalesce all concurrent callers
    if (!this.inflight.has(cacheKey)) {
      const fetchPromise = this.doFetch(cacheKey).finally(() => {
        this.inflight.delete(cacheKey);
      });
      this.inflight.set(cacheKey, fetchPromise);
    }

    // All concurrent callers await the same promise — only one origin fetch occurs
    const data = await this.inflight.get(cacheKey)!;
    return Response.json(JSON.parse(data), { headers: { 'X-Cache': 'MISS' } });
  }

  private async doFetch(cacheKey: string): Promise<string> {
    const originUrl = `${this.env.ORIGIN_BASE_URL}${cacheKey}`;
    const res = await fetch(originUrl);
    if (!res.ok) throw new Error(`Origin returned ${res.status}`);

    const data = await res.json();
    const serialized = JSON.stringify(data);

    const now = Date.now();
    await this.state.storage.put<CacheEntry>(cacheKey, {
      data,
      cachedAt: now,
      expiresAt: now + 60_000,       // hard TTL: 60 seconds
      staleUntil: now + 300_000,     // stale-while-revalidate: 5 minutes
    });

    return serialized;
  }
}

interface CacheEntry {
  data: unknown;
  cachedAt: number;
  expiresAt: number;
  staleUntil: number;
}
```

```typescript
// src/handlers/product.ts — routing to the DO

export async function getProduct(
  productId: string,
  env: Env,
): Promise<Response> {
  // All requests for the same productId route to the SAME DO instance
  const doId = env.CACHING_DO.idFromName(`product:${productId}`);
  const stub = env.CACHING_DO.get(doId);

  return stub.fetch(new Request(`https://internal/products/${productId}`));
}
```

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "CACHING_DO"
class_name = "CachingDO"

[[migrations]]
tag = "v1"
new_classes = ["CachingDO"]
```

---

## Pattern 2: KV Lock (Lightweight Coalescing without DO)

When a full Durable Object is too heavyweight, a KV-based mutex can limit
concurrent origin fetches. This is eventually consistent (not perfectly
serialized like a DO) but dramatically reduces stampede burst size:

```typescript
const LOCK_TTL_SECONDS = 10;

async function getWithKvLock(
  key: string,
  env: Env,
  fetcher: () => Promise<string>,
): Promise<string> {
  // Check KV cache
  const cached = await env.KV.get(key);
  if (cached !== null) return cached;

  // Try to acquire a lock by writing a sentinel value
  const lockKey = `lock:${key}`;
  const existingLock = await env.KV.get(lockKey);

  if (existingLock !== null) {
    // Another Worker has the lock — poll briefly then serve stale or 503
    await delay(200);
    const retried = await env.KV.get(key);
    if (retried !== null) return retried;
    throw new Error('Cache still empty after lock wait');
  }

  // Acquire lock
  await env.KV.put(lockKey, '1', { expirationTtl: LOCK_TTL_SECONDS });

  try {
    const value = await fetcher();
    await env.KV.put(key, value, { expirationTtl: 300 });
    return value;
  } finally {
    await env.KV.delete(lockKey);
  }
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
```

**Limitation**: KV is eventually consistent. Two Workers on different PoPs can
both miss the lock key and both fetch the origin. This reduces stampedes rather
than eliminating them. For true serialization, use the Durable Object approach.

---

## Pattern 3: Cache-Control SWR with the Cloudflare Cache API

For public, cacheable HTTP responses, configure `stale-while-revalidate` in the
`Cache-Control` header. Cloudflare's CDN layer handles the coalescing
transparently at the edge:

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cache = caches.default;
    const cacheKey = new Request(request.url, request);

    // Check the Cloudflare edge cache
    let response = await cache.match(cacheKey);
    if (response) return response;

    // Cache miss: fetch origin
    const originResponse = await fetch(env.ORIGIN_URL + new URL(request.url).pathname);
    const data = await originResponse.json();

    response = Response.json(data, {
      headers: {
        // Fresh for 60s, serve stale for up to 300s while revalidating in background
        'Cache-Control': 'public, max-age=60, stale-while-revalidate=300',
      },
    });

    // Store in Cloudflare's edge cache
    await cache.put(cacheKey, response.clone());
    return response;
  },
};
```

The Cloudflare CDN collapses concurrent cache-miss requests for the same URL at
each PoP — only one origin request leaves the PoP during revalidation.

---

## Choosing the Right Approach

| Scenario | Recommended approach |
|---|---|
| Expensive per-entity data (product, user profile) | Durable Object coalescing |
| Shared aggregate (homepage stats, leaderboard) | KV lock or Materialized View |
| Public HTTP responses, CDN-cacheable | Cache-Control SWR |
| DB-backed read with infrequent writes | Materialized view + Cron refresh |
| Global singleton (exchange rate, config) | Single DO instance per key |

---

## Anti-patterns

**Ignoring the stampede problem entirely**
Assuming "KV is fast enough" underestimates concurrent burst amplification.
During a TTL expiry + traffic spike, origin load spikes by the concurrency
factor, not the request rate.

**Setting TTL = 0 on hot keys**
Disabling caching on a high-traffic key to avoid staleness causes every request
to hit the origin — equivalent to a permanent stampede.

**Using a KV lock with long TTL**
If the lock-holding Worker crashes before deleting the lock, all other Workers
are blocked until the TTL expires. Keep lock TTL short (≤10 s) and ensure the
`finally` block always deletes the lock.

**Coalescing across DO instances**
`idFromName()` routes requests to a DO deterministically. Accidentally using
different name strings for the same logical key (e.g. with/without trailing
slash) creates multiple DO instances and no coalescing.

---

## Gotchas

- **DO in-memory `inflight` map is lost on DO eviction**: Durable Objects are
  evicted from memory after ~10 s of inactivity. A new DO activation rebuilds
  from `state.storage`. The first request after eviction hits the origin; this
  is acceptable.

- **`state.storage.get()` is async**: All DO storage reads involve an async hop
  to the DO's SQLite storage layer. For extremely hot keys (thousands of
  requests per second), the DO itself becomes a bottleneck. Consider a two-tier
  approach: Cache API (PoP-level) → DO (coalescing) → origin.

- **KV consistency**: KV reads from the nearest replica; writes propagate within
  ~60 s globally. A `put()` from one Worker may not be visible to another Worker
  on a different PoP for up to a minute. KV-based locks are best-effort.

- **SWR and personalized responses**: Never apply stale-while-revalidate to
  responses that vary by user identity. Use `Vary: Cookie` or `Vary: Authorization`
  headers to scope cache keys, or use DO coalescing with user-scoped keys.

---

## Verification

```bash
# 1. Load test a cold cache to observe stampede without the pattern
# (observe origin hit count = N concurrent requests)

# 2. Deploy DO coalescing and repeat
# (observe origin hit count ≈ 1, others served from DO in-memory state)

# 3. Check X-Cache headers
curl -sv https://api.example.com/products/prod_123 2>&1 | grep x-cache

# 4. Simulate TTL expiry: wait for cached.expiresAt, send burst
# (observe single origin fetch, all other responses receive stale or wait)

# 5. Inspect DO storage to verify cache entry was written
wrangler durable-objects inspect CachingDO product:prod_123
```

---

## Related

- `cache-aside-kv-d1-fallback.md` — basic KV-backed cache without stampede
  protection.
- `token-bucket-durable-objects.md` — another pattern using DO as a single-writer
  actor for rate state.
- `per-tenant-durable-object.md` — routing strategy for DO instance naming.
- `materialized-view-d1-workers.md` — pre-computing expensive aggregates to avoid
  cache misses on complex queries.
- `scatter-gather-parallel-workers.md` — the opposite problem: fanning out to
  many sources, then caching the merged result with this pattern.

---

## Sources

- Cloudflare Durable Objects documentation:
  https://developers.cloudflare.com/durable-objects/
- Cloudflare Cache API documentation:
  https://developers.cloudflare.com/workers/runtime-apis/cache/
- MDN — Cache-Control: stale-while-revalidate:
  https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control#stale-while-revalidate
- "Stampeding Herds" — original problem framing:
  https://en.wikipedia.org/wiki/Cache_stampede
- Cloudflare KV consistency model:
  https://developers.cloudflare.com/kv/reference/how-kv-works/
