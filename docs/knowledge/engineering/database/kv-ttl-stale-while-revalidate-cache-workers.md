# KV TTL & Stale-While-Revalidate Cache Pattern in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Worker fetches data from D1 or an external API on every request. Cache-aside with KV reduces
latency, but a hard TTL means users get a stale-or-miss flip: either they always see fresh data
(expensive) or they occasionally see a cold-start delay when the TTL expires (jarring). You want
the KV cache to **always respond immediately** while refreshing in the background when data is
stale.

## Context

The **stale-while-revalidate (SWR)** pattern returns cached data immediately even if it is past
its freshness window, then triggers an async revalidation so the *next* request sees fresh data.
Cloudflare KV's `expirationTtl` controls hard eviction; SWR is implemented as a separate
`staleAt` timestamp embedded in the cached value. The combination eliminates cold-start latency
while bounding staleness.

Workers' `waitUntil` API lets the revalidation fetch happen after the response is returned to the
client, with no added latency.

---

## KV Value Envelope

```typescript
// src/cache/types.ts
export interface CacheEntry<T> {
  data:     T;
  cachedAt: number;   // Unix ms
  staleAt:  number;   // Unix ms — SWR window starts here
  // KV hard TTL (expirationTtl) is set separately and should be > staleTtl
}

export interface CacheOptions {
  freshTtlMs: number;   // how long data is "fresh" (serve without revalidating)
  staleTtlMs: number;   // how long to serve stale data while revalidating in background
  // KV expirationTtl = (staleTtl / 1000) + buffer, set as seconds
}
```

---

## Cache Read/Write Helpers

```typescript
// src/cache/kv.ts
import type { CacheEntry, CacheOptions } from "./types";

export async function cacheGet<T>(
  kv: KVNamespace,
  key: string
): Promise<CacheEntry<T> | null> {
  const raw = await kv.get(key, "json");
  return raw as CacheEntry<T> | null;
}

export async function cachePut<T>(
  kv: KVNamespace,
  key: string,
  data: T,
  opts: CacheOptions
): Promise<void> {
  const now    = Date.now();
  const entry: CacheEntry<T> = {
    data,
    cachedAt: now,
    staleAt:  now + opts.freshTtlMs,
  };
  // Hard TTL = freshTtl + staleTtl (in seconds), so KV keeps the key available
  // during the stale window even if we haven't revalidated yet.
  const expirationTtl = Math.ceil((opts.freshTtlMs + opts.staleTtlMs) / 1000);
  await kv.put(key, JSON.stringify(entry), { expirationTtl });
}
```

---

## SWR Fetch Wrapper

```typescript
// src/cache/swr.ts
import { cacheGet, cachePut } from "./kv";
import type { CacheOptions } from "./types";

export interface SwrResult<T> {
  data:        T;
  fromCache:   boolean;
  wasStale:    boolean;
}

export async function swrFetch<T>(
  kv:       KVNamespace,
  ctx:      ExecutionContext,
  cacheKey: string,
  fetcher:  () => Promise<T>,
  opts:     CacheOptions
): Promise<SwrResult<T>> {
  const cached = await cacheGet<T>(kv, cacheKey);
  const now    = Date.now();

  if (cached) {
    const isFresh = now < cached.staleAt;
    if (!isFresh) {
      // Stale — serve immediately, revalidate in background
      ctx.waitUntil(
        fetcher().then((fresh) => cachePut(kv, cacheKey, fresh, opts)).catch(console.error)
      );
    }
    return { data: cached.data, fromCache: true, wasStale: !isFresh };
  }

  // Cache miss — fetch synchronously
  const data = await fetcher();
  ctx.waitUntil(cachePut(kv, cacheKey, data, opts).catch(console.error));
  return { data, fromCache: false, wasStale: false };
}
```

---

## Usage in a Worker Handler

```typescript
// src/handlers/products.ts
import { swrFetch } from "../cache/swr";

export async function handleGetProduct(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const productId = new URL(request.url).searchParams.get("id")!;
  const cacheKey  = `product:${productId}`;

  const { data: product, fromCache, wasStale } = await swrFetch(
    env.CACHE,       // KVNamespace binding
    ctx,
    cacheKey,
    () =>
      env.DB.prepare(
        "SELECT id, name, price, stock FROM products WHERE id = ?1"
      )
        .bind(productId)
        .first(),
    {
      freshTtlMs: 30_000,  // serve fresh for 30 s
      staleTtlMs: 120_000, // serve stale for up to 2 min while revalidating
    }
  );

  if (!product) return Response.json({ error: "Not found" }, { status: 404 });

  return Response.json(product, {
    headers: {
      "X-Cache":       fromCache ? "HIT" : "MISS",
      "X-Cache-Stale": wasStale  ? "true" : "false",
    },
  });
}
```

---

## Cache Invalidation on Write

When a product is updated, explicitly delete the KV key so the next read fetches fresh:

```typescript
// src/handlers/products.ts (continued)
export async function handleUpdateProduct(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const { id, name, price } =
    await request.json<{ id: string; name: string; price: number }>();

  await env.DB.prepare(
    "UPDATE products SET name = ?1, price = ?2 WHERE id = ?3"
  ).bind(name, price, id).run();

  // Invalidate the KV cache entry immediately
  ctx.waitUntil(env.CACHE.delete(`product:${id}`));

  return Response.json({ success: true });
}
```

---

## Namespace-Level Bulk Invalidation

For cache-busting an entire category (e.g., after a bulk price update):

```typescript
export async function invalidateProductCategory(
  env: Env,
  ctx: ExecutionContext,
  categoryId: string
): Promise<void> {
  // KV list + delete is the only bulk invalidation option
  // Prefix keys for efficient listing: "cat:{categoryId}:product:{productId}"
  const list = await env.CACHE.list({ prefix: `cat:${categoryId}:product:` });
  ctx.waitUntil(
    Promise.all(list.keys.map((k) => env.CACHE.delete(k.name)))
  );
}
```

---

## Anti-patterns

- **Using only KV's `expirationTtl` as the sole freshness control**: this creates hard miss spikes
  when many requests hit the same expired key simultaneously (thundering herd). SWR avoids this by
  always returning a cached value during revalidation.
- **Revalidating synchronously before returning the response**: eliminates the latency benefit; use
  `ctx.waitUntil` for background revalidation.
- **Ignoring `waitUntil` errors**: a silent failure leaves the cache stale indefinitely. Always
  attach `.catch(console.error)` or send errors to an observability sink.
- **Storing large objects in KV**: KV has a 25 MB per-value limit, but large values increase
  read latency. For blobs > 1 MB, store in R2 and cache only the metadata in KV.

---

## Gotchas

- KV write consistency is **eventually consistent** globally — a freshly written key may not be
  visible in all regions for up to 60 s. For latency-sensitive writes, prefer D1's Sessions API
  (`read-your-writes`) over KV.
- `expirationTtl` minimum is **60 seconds**. A `freshTtlMs` of 30 s still needs
  `expirationTtl ≥ 60`. Adjust your `staleTtlMs` to ensure `(freshTtlMs + staleTtlMs) / 1000 ≥ 60`.
- `ctx.waitUntil` callbacks must complete within **30 seconds** after the response is sent.
  Long-running revalidation (e.g., aggregate queries) should be offloaded to a Queue Worker instead.
- KV `list()` returns at most 1,000 keys per call — paginate with `cursor` for bulk invalidation of
  large namespaces.

---

## Verification

```bash
# First request: cache miss
curl -I https://example project.example.com/products?id=p-1
# X-Cache: MISS

# Second request within freshTtlMs: fresh cache hit
curl -I https://example project.example.com/products?id=p-1
# X-Cache: HIT  X-Cache-Stale: false

# After freshTtlMs but within staleTtlMs: stale hit + background revalidation
sleep 31
curl -I https://example project.example.com/products?id=p-1
# X-Cache: HIT  X-Cache-Stale: true
```

---

## Related

- `d1-kv-cache-aside-pattern-workers.md`
- `d1-materialized-view-simulation-cron.md`
- `d1-sessions-api-read-your-writes-workers.md`
- `query-caching-patterns.md`
- `redis-caching-patterns.md`

## Sources

- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- Workers ExecutionContext.waitUntil: https://developers.cloudflare.com/workers/runtime-apis/context/
- KV limits and guarantees: https://developers.cloudflare.com/kv/platform/limits/
