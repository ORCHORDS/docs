# Read-Through Cache Pattern with KV in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Every request to a Worker fetches the same product catalogue entry from D1 or an upstream API. At 5,000 RPS, this saturates the upstream and adds 50–150 ms of database latency to each response. The data changes at most once per hour.

You need a transparent cache that intercepts reads, serves cached values instantly, and populates itself on a miss — without the caller knowing whether the data came from cache or origin.

---

## Context

Cloudflare Workers KV is a globally distributed, eventually consistent key-value store. Reads served from the local PoP take ~1 ms. Writes propagate globally within ~60 seconds. KV is ideal for read-heavy, infrequently mutating data.

Read-through cache characteristics:
- The cache is authoritative for the caller — it always calls the cache, never the origin directly.
- On a cache miss, the cache layer fetches from origin, stores the result, and returns it.
- The cache is transparent — callers do not implement cache-miss logic.

Distinct from cache-aside (where the caller checks the cache, calls the origin on miss, and writes to the cache itself).

---

## Solution

### Core cache layer

```typescript
// cache/src/kv-read-through.ts
export interface CacheOptions {
  ttlSeconds: number;
  negativeTtlSeconds?: number; // TTL for "not found" results
  staleWhileRevalidate?: boolean;
}

export interface CacheEntry<T> {
  value: T | null; // null represents a negative cache entry
  cachedAt: number; // unix ms
  stale?: boolean; // set by caller after freshness check
}

export type OriginFetcher<T> = (key: string) => Promise<T | null>;

export class KVReadThrough<T> {
  constructor(
    private readonly kv: KVNamespace,
    private readonly fetcher: OriginFetcher<T>,
    private readonly options: CacheOptions,
  ) {}

  private cacheKey(key: string): string {
    // Namespace to prevent collisions with other KV consumers
    return `rthru:v1:${key}`;
  }

  async get(key: string): Promise<T | null> {
    const ck = this.cacheKey(key);
    const cached = await this.kv.get<CacheEntry<T>>(ck, 'json');

    if (cached !== null) {
      const ageMs = Date.now() - cached.cachedAt;
      const ttlMs = this.options.ttlSeconds * 1000;
      const isStale = ageMs > ttlMs;

      if (!isStale) {
        // Cache hit — serve immediately
        return cached.value;
      }

      if (this.options.staleWhileRevalidate) {
        // Serve stale, revalidate in background (fire-and-forget)
        // Note: ctx.waitUntil not available here — caller must handle this
        this.revalidate(key, ck);
        return cached.value;
      }
      // Stale and no SWR — fall through to origin fetch
    }

    // Cache miss or expired — fetch from origin
    return this.fetchAndCache(key, ck);
  }

  async invalidate(key: string): Promise<void> {
    await this.kv.delete(this.cacheKey(key));
  }

  private async fetchAndCache(key: string, ck: string): Promise<T | null> {
    const value = await this.fetcher(key);

    const ttl = value === null
      ? (this.options.negativeTtlSeconds ?? Math.min(this.options.ttlSeconds, 60))
      : this.options.ttlSeconds;

    const entry: CacheEntry<T> = { value, cachedAt: Date.now() };
    // Fire-and-forget — do not block the response on the KV write
    this.kv.put(ck, JSON.stringify(entry), { expirationTtl: ttl * 2 }); // 2x TTL so we can serve stale

    return value;
  }

  private revalidate(key: string, ck: string): void {
    // Background revalidation — errors are swallowed intentionally
    this.fetchAndCache(key, ck).catch((err) => {
      console.error(JSON.stringify({ type: 'cache_revalidation_error', key, error: String(err) }));
    });
  }
}
```

### Origin fetcher — D1 example

```typescript
// cache/src/product-cache.ts
import { KVReadThrough } from './kv-read-through';

export interface Product {
  id: string;
  name: string;
  priceCents: number;
  category: string;
  updatedAt: string;
}

export function createProductCache(
  kv: KVNamespace,
  db: D1Database,
): KVReadThrough<Product> {
  const fetcher = async (productId: string): Promise<Product | null> => {
    const row = await db
      .prepare('SELECT id, name, price_cents, category, updated_at FROM products WHERE id = ?')
      .bind(productId)
      .first<{ id: string; name: string; price_cents: number; category: string; updated_at: string }>();

    if (!row) return null;

    return {
      id: row.id,
      name: row.name,
      priceCents: row.price_cents,
      category: row.category,
      updatedAt: row.updated_at,
    };
  };

  return new KVReadThrough<Product>(kv, fetcher, {
    ttlSeconds: 3600,        // 1 hour — product data changes rarely
    negativeTtlSeconds: 300, // 5 minutes for 404s — prevents origin stampede on invalid IDs
    staleWhileRevalidate: true,
  });
}
```

### Cache key derivation — parameterised queries

```typescript
// cache/src/cache-key.ts
import { createHash } from 'node:crypto'; // available in Workers via the Web Crypto API shim

// For Workers, use the Web Crypto API instead of Node.js crypto
export async function deriveCacheKey(parts: string[]): Promise<string> {
  const raw = parts.join(':');
  const encoded = new TextEncoder().encode(raw);
  const digest = await crypto.subtle.digest('SHA-256', encoded);
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return hex.slice(0, 32); // 32-char hex prefix is sufficient for uniqueness
}

// Example: derive key for a paginated product list query
export async function productListKey(category: string, page: number, pageSize: number): Promise<string> {
  return deriveCacheKey(['product_list', category, String(page), String(pageSize)]);
}
```

### Worker entry point with stale-while-revalidate via waitUntil

```typescript
// worker/src/index.ts
import { createProductCache } from '../cache/src/product-cache';

export interface Env {
  KV_CACHE: KVNamespace;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const productId = url.pathname.replace('/products/', '');

    if (!productId || productId === '/products/') {
      return new Response('Bad Request', { status: 400 });
    }

    const cache = createProductCache(env.KV_CACHE, env.DB);

    // Check KV directly for SWR awareness
    const ck = `rthru:v1:${productId}`;
    const cached = await env.KV_CACHE.get<{ value: unknown; cachedAt: number }>(ck, 'json');
    const ttlMs = 3600 * 1000;
    const isStale = cached ? Date.now() - cached.cachedAt > ttlMs : false;

    const product = await cache.get(productId);

    if (product === null) {
      return new Response(JSON.stringify({ error: 'not_found' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // If stale, schedule a background revalidation via waitUntil
    if (isStale) {
      ctx.waitUntil(
        (async () => {
          try {
            await cache.invalidate(productId);
            await cache.get(productId); // repopulates
          } catch (err) {
            console.error(JSON.stringify({ type: 'swr_revalidation_error', productId, error: String(err) }));
          }
        })(),
      );
    }

    return new Response(JSON.stringify(product), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': isStale ? 'stale-while-revalidate=3600' : `max-age=${ttlMs / 1000}`,
        'X-Cache': cached ? (isStale ? 'STALE' : 'HIT') : 'MISS',
      },
    });
  },
};
```

### TTL strategy by data class

```typescript
// Recommended TTL values by data freshness class
const TTL_CONFIG = {
  // Static reference data — changes require a deployment
  static: { ttlSeconds: 86400, negativeTtlSeconds: 3600 },

  // Slow-moving data — pricing, catalogue, config
  slowMoving: { ttlSeconds: 3600, negativeTtlSeconds: 300, staleWhileRevalidate: true },

  // Semi-realtime — inventory levels, session state
  semiRealtime: { ttlSeconds: 60, negativeTtlSeconds: 10, staleWhileRevalidate: true },

  // Do not cache — financial balances, OTP state, auth tokens
  doNotCache: null,
} as const;
```

---

## Implementation Details

**KV consistency:** KV is eventually consistent with a ~60-second propagation window. Do not use it for data where two Workers in different PoPs must agree within that window (e.g., inventory counts, rate limits). Use Durable Objects for strong consistency.

**Negative caching:** Without negative caching, a flood of requests for a non-existent resource (invalid product IDs scraped from an old sitemap) hits the origin on every request. Cache `null` results with a shorter TTL.

**Cache stampede:** On a cold start or after a mass invalidation, many concurrent Workers may simultaneously miss the cache and call the origin. Mitigate with:
- Stale-while-revalidate (serve old data while one Worker revalidates).
- Durable Objects as a coordinated cache population lock for high-value keys.

**KV write costs:** Each `kv.put()` is a write operation billed per-write. For very high write rates (>1 M/day), ensure TTL is long enough that cache hits amortise write cost.

**`expirationTtl` vs `expiration`:** Use `expirationTtl` (relative, in seconds) rather than `expiration` (absolute unix timestamp) to avoid clock skew issues.

---

## Anti-patterns

- **Caching inside the Worker without KV:** V8 isolates are ephemeral; in-memory caches vanish on cold starts and are not shared between isolate instances. KV is the correct shared store.
- **Using KV for write-heavy data:** KV is optimised for reads. If you write more than you read, consider D1 or Durable Objects.
- **Caching sensitive user data in a shared namespace:** KV keys are shared across all requests. Ensure cache keys include user-scoped identifiers or store user data in Durable Objects.
- **TTL longer than the staleness tolerance of the business:** A 24-hour TTL on pricing data means a price change takes 24 hours to propagate. Define TTLs in terms of business tolerance, not technical convenience.
- **Blocking the response on the KV write:** `await kv.put(...)` adds the KV write latency to every cache-miss response. Fire-and-forget the write and let `ctx.waitUntil` extend the Worker's lifetime if needed.

---

## Gotchas

- KV values are limited to 25 MB. Large payloads (image metadata, bulk catalogue exports) should be stored in R2; store only the R2 key in KV.
- `kv.get()` returns `null` both for keys that do not exist and for keys whose value was explicitly set to `null`. Wrap values in a container object (`{ value: ... }`) to distinguish a cached null from a cache miss.
- KV list operations (`kv.list()`) are strongly consistent only within the same PoP; do not use them for cache coherence logic.
- `ctx.waitUntil()` extends the Worker's lifetime after `Response` is returned but has a limit of 30 seconds total. Do not schedule long-running revalidations inside it.
- Wrangler local dev uses an in-process KV mock that does not replicate eventually-consistent behaviour. Test SWR logic in a preview environment, not locally.

---

## Verification

1. Send 10 requests for the same product ID. Confirm: first request logs `X-Cache: MISS`, subsequent 9 log `X-Cache: HIT`.
2. Expire the cache entry by setting a 1-second TTL in a test build. Wait 2 seconds and send a request. Confirm `X-Cache: STALE` is returned and a background revalidation fires.
3. Request a non-existent product ID 100 times in 10 seconds. Confirm origin is called once (on the first miss) and the 404 response is cached for `negativeTtlSeconds`.
4. Run `wrangler kv:key list` on the cache namespace. Confirm entries match the `rthru:v1:` prefix scheme.

---

## Related

- `workers-scatter-gather-parallel-fetch.md` — caching individual upstream results before scatter
- `workers-outbox-pattern-d1-queues.md` — cache invalidation events via outbox on data mutation
- Cloudflare KV documentation: https://developers.cloudflare.com/kv/

---

## Sources

- Designing Data-Intensive Applications — Martin Kleppmann, Chapter 5: Replication (eventual consistency)
- Cloudflare KV: https://developers.cloudflare.com/kv/api/
- Cloudflare Workers Runtime APIs — ExecutionContext.waitUntil: https://developers.cloudflare.com/workers/runtime-apis/context/
