# Cache-Aside Pattern with Workers KV and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker queries D1 on every request for data that changes infrequently — product catalogue rows, user profiles, configuration records. D1 read latency and cost accumulate under load. Wrapping D1 reads in a KV-backed cache-aside layer dramatically reduces both, while a single-flight lock prevents cache stampedes when the entry is cold.

---

## Context

Cache-aside (lazy loading) keeps the application in charge: on a cache miss the Worker fetches from D1, writes the result to KV with a TTL, and serves the response. On a cache hit the Worker skips D1 entirely. KV's global replication means the cached value is served from the edge closest to the user. Cache invalidation deletes the KV key and optionally re-warms it immediately. A lightweight single-flight mechanism using KV's `ifNoneMatch` (via a lock key) prevents multiple simultaneous cold requests from all hitting D1 in parallel during a cache miss.

---

## Wrangler Config

```toml
[[d1_databases]]
binding       = "DB"
database_name = "app-db"
database_id   = "<your-d1-database-id>"

[[kv_namespaces]]
binding   = "CACHE"
id        = "<your-kv-namespace-id>"
preview_id = "<your-kv-preview-namespace-id>"
```

---

## Per-Route TTL Configuration

```typescript
// cache-config.ts
export const CACHE_TTL: Record<string, number> = {
  'product':       300,   // 5 min — product detail rows
  'user-profile':  60,    // 1 min — user data
  'config':        3600,  // 1 h   — rarely changed config
  'search-result': 30,    // 30 s  — search results
};

export function ttlFor(route: string): number {
  return CACHE_TTL[route] ?? 60;
}
```

---

## Implementation — Cache Helper

```typescript
// cache.ts

export interface CacheOptions {
  kv:         KVNamespace;
  ttl:        number;   // seconds
  lockTtl?:   number;   // seconds — default 5 s
}

/**
 * Read from KV; on miss, call fetchFn, write to KV, return value.
 * Uses a KV lock key to implement single-flight stampede protection.
 */
export async function getOrFetch<T>(
  key: string,
  opts: CacheOptions,
  fetchFn: () => Promise<T>
): Promise<T> {
  const { kv, ttl, lockTtl = 5 } = opts;

  // 1. Fast path: cache hit
  const cached = await kv.get<T>(key, 'json');
  if (cached !== null) return cached;

  // 2. Attempt to acquire a single-flight lock via ifNoneMatch
  const lockKey = `lock:${key}`;
  const lockAcquired = await tryAcquireLock(kv, lockKey, lockTtl);

  if (!lockAcquired) {
    // Another worker is fetching; poll KV briefly for the result
    return pollForResult<T>(kv, key, 2_000 /* ms */, fetchFn);
  }

  // 3. We hold the lock — fetch from source
  try {
    const value = await fetchFn();
    await kv.put(key, JSON.stringify(value), { expirationTtl: ttl });
    return value;
  } finally {
    await kv.delete(lockKey);
  }
}

/**
 * Delete the KV entry to invalidate the cache.
 * Pass rewarm=true to immediately re-populate from fetchFn.
 */
export async function invalidate<T>(
  key: string,
  kv: KVNamespace,
  rewarmFn?: () => Promise<T>,
  rewarmTtl?: number
): Promise<void> {
  await kv.delete(key);
  if (rewarmFn && rewarmTtl !== undefined) {
    const fresh = await rewarmFn();
    await kv.put(key, JSON.stringify(fresh), { expirationTtl: rewarmTtl });
  }
}

// --- Internal helpers ---

async function tryAcquireLock(
  kv: KVNamespace,
  lockKey: string,
  lockTtl: number
): Promise<boolean> {
  // KV does not expose true CAS, but putIfAbsent can be simulated:
  // read the lock key; if absent, write it. This is a best-effort
  // single-flight — under extreme concurrency two workers may both see
  // a miss and both fetch, which is safe (last write wins in KV).
  const existing = await kv.get(lockKey);
  if (existing !== null) return false;
  await kv.put(lockKey, '1', { expirationTtl: lockTtl });
  return true;
}

async function pollForResult<T>(
  kv: KVNamespace,
  key: string,
  maxWaitMs: number,
  fallbackFn: () => Promise<T>
): Promise<T> {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    await sleep(50);
    const value = await kv.get<T>(key, 'json');
    if (value !== null) return value;
  }
  // Lock holder took too long — fall through to fetch directly
  return fallbackFn();
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
```

---

## Implementation — Worker Entry-Point

```typescript
// worker.ts
import { getOrFetch, invalidate } from './cache';
import { ttlFor } from './cache-config';

export interface Env {
  DB:    D1Database;
  CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // GET /products/:id
    const productMatch = url.pathname.match(/^\/products\/([^/]+)$/);
    if (productMatch && request.method === 'GET') {
      const id      = productMatch[1];
      const cacheKey = `product:${id}`;
      const product  = await getOrFetch(
        cacheKey,
        { kv: env.CACHE, ttl: ttlFor('product') },
        () => fetchProductFromD1(env.DB, id)
      );
      return product
        ? Response.json(product)
        : new Response('Not found', { status: 404 });
    }

    // DELETE /products/:id/cache  — explicit invalidation
    const invalidateMatch = url.pathname.match(/^\/products\/([^/]+)\/cache$/);
    if (invalidateMatch && request.method === 'DELETE') {
      const id       = invalidateMatch[1];
      const cacheKey = `product:${id}`;
      await invalidate(
        cacheKey,
        env.CACHE,
        () => fetchProductFromD1(env.DB, id),  // re-warm immediately
        ttlFor('product')
      );
      return new Response(null, { status: 204 });
    }

    // GET /users/:id
    const userMatch = url.pathname.match(/^\/users\/([^/]+)$/);
    if (userMatch && request.method === 'GET') {
      const id      = userMatch[1];
      const cacheKey = `user-profile:${id}`;
      const user     = await getOrFetch(
        cacheKey,
        { kv: env.CACHE, ttl: ttlFor('user-profile') },
        () => fetchUserFromD1(env.DB, id)
      );
      return user
        ? Response.json(user)
        : new Response('Not found', { status: 404 });
    }

    return new Response('Not found', { status: 404 });
  },
};

async function fetchProductFromD1(
  db: D1Database,
  id: string
): Promise<Record<string, unknown> | null> {
  return db.prepare(
    `SELECT id, name, price_cents, category FROM products WHERE id = ?`
  ).bind(id).first();
}

async function fetchUserFromD1(
  db: D1Database,
  id: string
): Promise<Record<string, unknown> | null> {
  return db.prepare(
    `SELECT id, email, display_name, role FROM users WHERE id = ?`
  ).bind(id).first();
}
```

---

## Anti-patterns

- **Caching mutable transactional data** — Never cache data that changes within a business transaction (e.g. account balances mid-checkout); KV's eventual consistency can serve stale reads that cause over-commits.
- **Infinite TTL** — KV does not enforce stale-while-revalidate; a TTL of 0 (no expiry) means you must manually invalidate on every write or serve stale data forever.
- **Using the same key for different data shapes** — Key collisions between routes (e.g. `product:1` vs `user:1` both becoming `1` due to a formatting bug) serve wrong-type JSON to consumers.
- **Skipping invalidation on writes** — Updating D1 without deleting the KV key leaves the cache hot with stale data until the TTL expires.

---

## Gotchas

- KV reads inside a Worker are eventually consistent globally; a write in one region may not be visible to reads in another region for up to 60 seconds. Design your TTLs and invalidation strategy around this window.
- `kv.get()` counts against your KV read operations quota; for extremely hot keys (millions of reads/min), use the Workers Cache API (`caches.default`) as a first layer in front of KV.
- The lock in `tryAcquireLock` is a best-effort single-flight, not a distributed mutex; two Workers can both see a missing lock key simultaneously under very high concurrency. This is safe — it causes at most N parallel D1 fetches instead of 1.
- `kv.get<T>(key, 'json')` returns `null` on miss, not `undefined`; the `!== null` check is intentional and required.
- Re-warming on invalidation adds D1 latency to the DELETE response; do it asynchronously with `ctx.waitUntil` when response time matters.

---

## Verification

```bash
# Cold read — should hit D1 and populate KV
curl -i http://localhost:8787/products/prod-001

# Warm read — served from KV (observe D1 query logs stop)
curl -i http://localhost:8787/products/prod-001

# Inspect KV value
wrangler kv key get --namespace-id=<id> "product:prod-001"

# Explicit cache invalidation + re-warm
curl -X DELETE http://localhost:8787/products/prod-001/cache

# Confirm KV was re-populated
wrangler kv key get --namespace-id=<id> "product:prod-001"

# Verify TTL is set (check expirationTtl in list output)
wrangler kv key list --namespace-id=<id> --prefix="product:"
```

---

## Related

- `outbox-pattern-workers-d1-queues.md`
- `scatter-gather-workers-queues.md`
- `circuit-breaker-workers-durable-objects.md`

---

## Sources

- Cloudflare KV API — https://developers.cloudflare.com/kv/api/
- Cloudflare D1 Worker API — https://developers.cloudflare.com/d1/worker-api/
- Cache-Aside Pattern (Azure Architecture Center) — https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside
