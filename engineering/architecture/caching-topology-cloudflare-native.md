# Caching Topology for a Cloudflare-Native Stack

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

---

## Symptom / Use-case

Your application runs entirely on Cloudflare (Workers + D1 + KV + R2). Latency on read-heavy routes is dominated by D1 query time (~10–50 ms per query in the same region, higher cross-region). You want to introduce structured caching that reduces D1 pressure, keeps cold-start overhead low, and stays evictable when data changes — without pulling in Redis or an external cache cluster.

---

## Context

A Cloudflare-native stack has four natural caching tiers, each with different latency, capacity, TTL semantics, and invalidation options:

```
Tier 1  →  Cloudflare CDN (edge cache / Cache API)
Tier 2  →  Workers Cache API (per-PoP programmatic cache)
Tier 3  →  Workers KV (global eventually-consistent KV store)
Tier 4  →  D1 (source of truth; SQLite; ~10–50 ms per query)
```

Each tier sits closer to the user than the next, but has progressively less control over eviction. Understanding which tier to use for which data pattern — and how to compose them — is the core of Cloudflare-native caching architecture.

---

## Tier Characteristics

| Tier | Latency | Scope | TTL Control | Invalidation | Best for |
|---|---|---|---|---|---|
| CDN / Cache API (GET responses) | <5 ms (cache hit) | Per-PoP | `Cache-Control` header | `cache.delete()` or tag purge | Public, immutable-ish GET responses |
| Workers Cache API (internal) | <5 ms (hit) | Per-PoP | API-set TTL | `cache.delete(request)` | Per-Worker derived responses |
| Workers KV | 0–35 ms | Global (eventual) | Key-level TTL | Key overwrite + eventual | Shared config, session state, feature flags |
| D1 | 10–50 ms | Single region primary | No built-in cache | N/A (write-through) | Source of truth |

"Per-PoP" means the cache is local to the Cloudflare Point of Presence (PoP) handling the request. Two users served by different PoPs have separate per-PoP caches that do not share state.

---

## Tier 1: CDN Edge Cache for Public Responses

For fully public, cacheable HTTP responses (e.g. product listings, public API endpoints), let Cloudflare's CDN cache the response at the edge without any Worker code involved:

```typescript
// src/handlers/products-handler.ts
export async function handleProductList(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response> {
  // Check CDN cache first (automatic if Cache-Control allows it)
  // For fine-grained control, use the Cache API:
  const cache = caches.default;
  const cacheKey = new Request(request.url, { method: 'GET' });

  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  // Cache miss: build response from KV or D1 (see tiers below)
  const data = await buildProductList(env);
  const response = Response.json(data, {
    headers: {
      'Cache-Control': 'public, max-age=60, stale-while-revalidate=300',
      'Vary':          'Accept-Encoding',
    },
  });

  // Store in CDN cache for subsequent requests from same PoP
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}
```

**Key rules**:
- Only `GET` and `HEAD` responses are cacheable via the Cache API.
- Never cache responses that include user-specific data with a public `Cache-Control`.
- Use `stale-while-revalidate` to serve stale content immediately while the Worker fetches a fresh copy in the background.

---

## Tier 2: Workers Cache API for Derived/Personalized Responses

For responses that are expensive to compute but are user-specific or cannot be cached by the CDN, use the Cache API with a per-user cache key:

```typescript
// src/handlers/user-dashboard.ts
export async function handleDashboard(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  userId: string,
): Promise<Response> {
  const cache = caches.default;

  // Namespace the cache key with the user ID
  const cacheKey = new Request(
    `https://internal-cache.local/dashboard/${userId}`,
    { method: 'GET' }
  );

  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  // Build from KV or D1
  const dashboard = await buildDashboard(env, userId);
  const response = Response.json(dashboard, {
    headers: {
      // Private: do not let the CDN share this across users
      'Cache-Control': 'private, max-age=30',
    },
  });

  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

// Invalidate a specific user's cached dashboard on writes
export async function invalidateDashboard(
  userId: string,
): Promise<void> {
  const cache = caches.default;
  await cache.delete(
    new Request(`https://internal-cache.local/dashboard/${userId}`)
  );
}
```

The internal hostname (`internal-cache.local`) is a convention: the Cache API uses the full URL as the cache key, so any string that uniquely identifies the cached resource works. It never resolves as an actual hostname.

---

## Tier 3: Workers KV as a Global Shared Cache

Workers KV is the right tier for data that is:
- Read far more often than written (KV has eventual consistency with ~60 s propagation lag).
- Needed globally across all PoPs (e.g. feature flags, tenant configuration, session tokens).
- Acceptable to be stale for up to the KV propagation window.

```typescript
// src/cache/kv-cache.ts

const KV_CACHE_TTL_SECONDS = 300; // 5 minutes

export async function getOrSetKV<T>(
  kv: KVNamespace,
  key: string,
  fallback: () => Promise<T>,
  ttlSeconds = KV_CACHE_TTL_SECONDS,
): Promise<T> {
  // 1. Try KV first
  const cached = await kv.get<T>(key, 'json');
  if (cached !== null) return cached;

  // 2. Miss: call the fallback (typically a D1 query)
  const value = await fallback();

  // 3. Write back to KV asynchronously (don't block the response)
  //    Use ctx.waitUntil in the outer scope if available; here we fire-and-forget
  void kv.put(key, JSON.stringify(value), { expirationTtl: ttlSeconds });

  return value;
}

// Usage example
export async function getTenantConfig(
  env: Env,
  tenantId: string,
): Promise<TenantConfig> {
  return getOrSetKV(
    env.TENANT_CONFIG_KV,
    `tenant:${tenantId}:config`,
    async () => {
      const row = await env.DB.prepare(
        `SELECT * FROM tenant_configs WHERE id = ?`
      ).bind(tenantId).first<TenantConfig>();
      if (!row) throw new Error(`Tenant ${tenantId} not found`);
      return row;
    },
    600, // 10-minute TTL
  );
}

// Write-through invalidation: update D1, then invalidate KV
export async function updateTenantConfig(
  env: Env,
  tenantId: string,
  patch: Partial<TenantConfig>,
): Promise<void> {
  // 1. Write to D1
  await env.DB.prepare(
    `UPDATE tenant_configs SET plan = ?, updated_at = ? WHERE id = ?`
  ).bind(patch.plan, new Date().toISOString(), tenantId).run();

  // 2. Invalidate KV immediately (next read will re-populate)
  await env.TENANT_CONFIG_KV.delete(`tenant:${tenantId}:config`);
}
```

---

## Tier 4: D1 Query-Level Caching (In-Worker)

Even within a single Worker invocation, it is worth caching D1 query results in a plain JavaScript `Map` to avoid redundant queries for the same data within one request's lifetime:

```typescript
// src/cache/request-scope-cache.ts

/**
 * A simple per-request in-memory cache backed by a Map.
 * Lives only for the duration of the Worker invocation.
 */
export class RequestScopeCache {
  private store = new Map<string, unknown>();

  async get<T>(
    key: string,
    loader: () => Promise<T>,
  ): Promise<T> {
    if (this.store.has(key)) {
      return this.store.get(key) as T;
    }
    const value = await loader();
    this.store.set(key, value);
    return value;
  }

  invalidate(key: string): void {
    this.store.delete(key);
  }
}

// Usage in a handler
export async function handleOrderDetails(
  request: Request,
  env: Env,
  reqCache: RequestScopeCache,
  orderId: string,
): Promise<Response> {
  // Called multiple times in one request? D1 only hit once.
  const order = await reqCache.get(`order:${orderId}`, () =>
    env.DB.prepare(`SELECT * FROM orders WHERE id = ?`)
      .bind(orderId)
      .first()
  );
  return Response.json(order);
}
```

---

## Composing All Four Tiers: Read Path Decision Tree

```
Incoming GET /products?category=shoes
         │
         ▼
[Tier 1] CDN edge cache hit? ──YES──► Return cached response (0 Worker invocations)
         │ NO
         ▼
Worker invoked
         │
[Tier 2] Cache API hit? ──YES──► Return + optionally refresh in background
         │ NO
         ▼
[Tier 3] KV.get("products:shoes") hit? ──YES──► Build response, store in Cache API, return
         │ NO
         ▼
[Tier 4] D1 query ──► Store result in KV ──► Store response in Cache API ──► Return
```

```typescript
// src/handlers/products-by-category.ts
export async function handleProductsByCategory(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  category: string,
): Promise<Response> {
  // Tier 2: Cache API
  const cache = caches.default;
  const cacheKey = new Request(`https://internal-cache.local/products/${category}`);
  const tier2Hit = await cache.match(cacheKey);
  if (tier2Hit) return tier2Hit;

  // Tier 3: Workers KV
  let products = await env.PRODUCTS_KV.get<Product[]>(`products:${category}`, 'json');

  if (!products) {
    // Tier 4: D1
    const result = await env.DB.prepare(
      `SELECT id, name, price_cents, stock FROM products WHERE category = ? AND active = 1`
    ).bind(category).all<Product>();
    products = result.results ?? [];

    // Write back to KV (Tier 3)
    ctx.waitUntil(
      env.PRODUCTS_KV.put(
        `products:${category}`,
        JSON.stringify(products),
        { expirationTtl: 300 },
      )
    );
  }

  const response = Response.json(products, {
    headers: { 'Cache-Control': 'public, max-age=60, stale-while-revalidate=240' },
  });

  // Write to Cache API (Tier 2)
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}
```

---

## Cache Invalidation Strategy

| Event | Action |
|---|---|
| Product updated via admin API | Delete KV key + delete Cache API key |
| Tenant config changed | Delete KV key; CDN key not applicable (private) |
| Bulk catalogue import | KV key overwrite with new TTL; Cache API purge via tag |
| Price change (time-sensitive) | Delete KV key; set short CDN TTL (≤10 s) proactively |

For bulk tag-based CDN purge, set `Cache-Tag` response headers and use Cloudflare's cache purge API:

```typescript
const response = Response.json(data, {
  headers: {
    'Cache-Control': 'public, max-age=300',
    'Cache-Tag':     `products,category:${category},tenant:${tenantId}`,
  },
});

// Purge via Cloudflare API when data changes
async function purgeCacheTag(tag: string, zoneId: string, apiToken: string) {
  await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ tags: [tag] }),
    }
  );
}
```

---

## Anti-patterns

- **Caching mutable user-specific data with `public` Cache-Control**: Cloudflare's CDN will serve one user's private data to another user hitting the same URL from the same PoP. Always use `private` or include user identity in the cache key.
- **Using KV for high-write data**: KV is optimised for read-heavy workloads. Writing more than once per second to the same key causes write coalescing and stale reads. Use D1 for frequently mutated data.
- **Not setting TTLs on KV entries**: KV entries without a TTL accumulate indefinitely and are never evicted. Always set `expirationTtl` in write-back paths.
- **Blocking response on cache writes**: Calling `await cache.put(...)` or `await kv.put(...)` inside the main response path adds latency. Wrap in `ctx.waitUntil()` to run asynchronously after the response is sent.
- **Caching errors**: Never cache a failed response (5xx). Check `response.ok` before calling `cache.put()`.
- **Over-caching with long TTLs**: A 1-hour CDN TTL on a product catalogue means price changes take 1 hour to reflect. Align TTLs with the business tolerance for stale data.

---

## Gotchas

- **Cache API is per-PoP**: A cache invalidation via `cache.delete()` only clears the cache in the PoP where the deleting Worker ran. For global invalidation, use Cloudflare's cache purge REST API or tag-based purge.
- **KV reads are eventually consistent**: After a KV write, reads from other PoPs may return the old value for up to ~60 seconds. Design for stale reads or use the `cacheTtl: 0` option on `kv.get()` to bypass the edge KV cache and force a read from the central store (higher latency).
- **D1 cross-region reads**: D1's primary resides in one region. Workers running in remote PoPs pay ~100–200 ms for cross-region D1 queries. The KV tier exists specifically to avoid this latency for read-heavy data.
- **Cache-Control `s-maxage`**: When you want different TTLs for the CDN and the browser, use `s-maxage` (CDN) alongside `max-age` (browser). Cloudflare respects `s-maxage` over `max-age` for edge caching.

---

## Verification

```bash
# 1. Confirm CDN is caching (look for CF-Cache-Status: HIT on second request)
curl -I https://myapp.workers.dev/products?category=shoes
curl -I https://myapp.workers.dev/products?category=shoes
# Expect: CF-Cache-Status: HIT on second call

# 2. Check KV value was written
wrangler kv key get "products:shoes" --namespace-id=<KV_NAMESPACE_ID>

# 3. Simulate cache invalidation
wrangler kv key delete "products:shoes" --namespace-id=<KV_NAMESPACE_ID>
curl -I https://myapp.workers.dev/products?category=shoes
# Expect: CF-Cache-Status: MISS, then D1 query logged

# 4. Verify Cache-Control headers are correct on public vs. private routes
curl -I https://myapp.workers.dev/dashboard   # Expect: Cache-Control: private
curl -I https://myapp.workers.dev/products    # Expect: Cache-Control: public
```

---

## Related

- `caching-layers-cloudflare-workers-kv-r2.md` — KV and R2 as storage/cache layers
- `cache-aside-pattern.md` — general cache-aside read pattern
- `feature-flag-cloudflare-workers-kv.md` — KV for feature flags (high-read config data)
- `read-through-cache.md` — read-through vs. cache-aside comparison
- `write-through-cache.md` — write-through invalidation strategies
- `cdn-architecture.md` — CDN fundamentals and edge caching concepts

---

## Sources

- Cloudflare Cache API documentation — https://developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare Workers KV documentation — https://developers.cloudflare.com/kv/
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Cloudflare Cache Rules — https://developers.cloudflare.com/cache/how-to/cache-rules/
- Cache-Control MDN reference — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
- Cloudflare cache purge API — https://developers.cloudflare.com/cache/how-to/purge-cache/
