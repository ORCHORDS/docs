# Cache Stampede Prevention with Workers and Durable Objects

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Under high traffic a popular cache entry expires and hundreds of concurrent Workers requests all miss simultaneously, flooding the origin or D1 with identical queries before the first response has been computed. This thundering-herd burst can saturate your database connection pool or trigger rate limits within milliseconds.

## Context

Cloudflare Workers are stateless and share no in-process memory, so classical mutex-based stampede guards cannot work. Durable Objects provide a single-threaded, strongly-consistent actor per key that can act as a per-resource coordinator. Combined with the Cache API (or KV) as the fast-path store, a DO acts as the exclusive filler: exactly one request recomputes the value while all others await the result via `fetch` coalescing inside the DO.

## Architecture Overview

```
Request → Workers fetch() → Cache API hit? → return cached value
                                  ↓ miss
                         DO stub (keyed by cache key)
                           ├─ already filling? → wait for promise
                           └─ leader: compute → write cache → resolve waiters
```

The DO holds a `Promise<Response>` per active fill. Followers attach to that promise rather than issuing their own origin requests.

## Durable Object: StampedeGuard

```typescript
// src/stampede-guard.ts
import { DurableObject } from "cloudflare:workers";

interface Env {
  STAMPEDE_GUARD: DurableObjectNamespace;
  DB: D1Database;
}

interface CachedEntry {
  value: unknown;
  expiresAt: number;
}

export class StampedeGuard extends DurableObject {
  private inflight: Map<string, Promise<unknown>> = new Map();

  async fetch(request: Request): Promise<Response> {
    const { key, ttl } = (await request.json()) as { key: string; ttl: number };

    // Check in-memory mini-cache (DO instance lives ~30 s idle)
    const stored = await this.ctx.storage.get<CachedEntry>(key);
    if (stored && stored.expiresAt > Date.now()) {
      return Response.json({ value: stored.value, source: "do-storage" });
    }

    // If a fill is already in progress, attach to it
    if (this.inflight.has(key)) {
      const value = await this.inflight.get(key)!;
      return Response.json({ value, source: "coalesced" });
    }

    // Become the leader: start the fill
    const fillPromise = this.fill(key, ttl);
    this.inflight.set(key, fillPromise);

    try {
      const value = await fillPromise;
      return Response.json({ value, source: "leader" });
    } finally {
      this.inflight.delete(key);
    }
  }

  private async fill(key: string, ttl: number): Promise<unknown> {
    // Derive the resource id from the key (key format: "product:{id}")
    const [type, id] = key.split(":");
    let value: unknown;

    if (type === "product") {
      const env = this.env as Env;
      const row = await env.DB.prepare(
        "SELECT * FROM products WHERE id = ?1"
      )
        .bind(id)
        .first();
      value = row;
    } else {
      throw new Error(`Unknown key type: ${type}`);
    }

    const entry: CachedEntry = { value, expiresAt: Date.now() + ttl * 1000 };
    await this.ctx.storage.put(key, entry, { expirationTtl: ttl });
    return value;
  }
}
```

## Worker: Cache-First with DO Fallback

```typescript
// src/worker.ts
import { StampedeGuard } from "./stampede-guard";

export { StampedeGuard };

interface Env {
  STAMPEDE_GUARD: DurableObjectNamespace;
  DB: D1Database;
}

const CACHE_TTL = 60; // seconds

async function getProductCached(
  env: Env,
  productId: string,
  cacheKey: string
): Promise<unknown> {
  // 1. Check Cloudflare Cache API (network-level, zero cost)
  const cache = caches.default;
  const cacheRequest = new Request(`https://internal/cache/${cacheKey}`);
  const cached = await cache.match(cacheRequest);
  if (cached) {
    return cached.json();
  }

  // 2. Cache miss — ask the DO guard to fill (stampede-safe)
  const doId = env.STAMPEDE_GUARD.idFromName(cacheKey);
  const stub = env.STAMPEDE_GUARD.get(doId);

  const doResponse = await stub.fetch("https://do/fill", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: cacheKey, ttl: CACHE_TTL }),
  });

  const { value } = (await doResponse.json()) as { value: unknown };

  // 3. Populate Cache API so future requests skip the DO entirely
  const toCache = new Response(JSON.stringify(value), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${CACHE_TTL}`,
    },
  });
  // cache.put is fire-and-forget from the Worker's perspective
  void cache.put(cacheRequest, toCache.clone());

  return value;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const match = url.pathname.match(/^\/products\/([^/]+)$/);
    if (!match) return new Response("Not Found", { status: 404 });

    const productId = match[1];
    const cacheKey = `product:${productId}`;

    try {
      const product = await getProductCached(env, productId, cacheKey);
      if (!product) return new Response("Not Found", { status: 404 });
      return Response.json(product);
    } catch (err) {
      console.error("Cache fill error", err);
      return new Response("Internal Server Error", { status: 500 });
    }
  },
};
```

## wrangler.toml Configuration

```toml
name = "stampede-prevention"
main = "src/worker.ts"
compatibility_date = "2024-09-23"

[[durable_objects.bindings]]
name = "STAMPEDE_GUARD"
class_name = "StampedeGuard"

[[migrations]]
tag = "v1"
new_classes = ["StampedeGuard"]

[[d1_databases]]
binding = "DB"
database_name = "products-db"
database_id = "YOUR_D1_ID"
```

## Key Tuning Parameters

| Parameter | Guideline | Rationale |
|-----------|-----------|-----------|
| `CACHE_TTL` | 30–300 s | Shorter = fresher; longer = fewer fills |
| DO idle eviction | ~30 s | Keep warm during burst window |
| DO `expirationTtl` | Match `CACHE_TTL` | Prevents DO storage bloat |
| `inflight` map size | Bounded by DO concurrency | Single-threaded, no explicit cap needed |

For keys with very high cardinality (millions of products), shard the DO namespace by a hash prefix to avoid a single DO becoming a hotspot:

```typescript
const shard = parseInt(productId, 36) % 64;
const doId = env.STAMPEDE_GUARD.idFromName(`shard-${shard}:${cacheKey}`);
```

## Anti-patterns

- **Bypassing the Cache API** — going to the DO on every request defeats the fast path; always check Cache API first so 99%+ of traffic never reaches the DO.
- **Keying the DO on the full URL** — query strings and auth tokens produce unique keys, destroying coalescing; normalize the key to the logical resource identity.
- **Unbounded inflight map** — if fills are extremely slow and many distinct keys miss simultaneously the map grows; add a cap and shed excess with 503.
- **Not propagating fill errors** — if `fill()` rejects, followers must also reject; swallowing errors leaves them waiting indefinitely.
- **Setting expirationTtl much shorter than CACHE_TTL** — the DO storage entry expires before Cache API entries, causing a gap where the DO guard cannot short-circuit a second miss wave.

## Gotchas

- The Cache API is keyed per `colo`, not globally; a burst spread across multiple PoPs triggers one fill per PoP, not one globally. For truly global deduplication keep DO storage TTL active.
- `cache.put()` requires a `Cache-Control` header or the response is not stored; Workers default to "no-store" for programmatic responses.
- DO `fetch()` calls count toward subrequest limits (1000/request); use the DO for the initial miss path only, not on every cache check.
- Durable Object storage `get()` is ~1 ms RTT within the same colo; it is significantly faster than a D1 query for the guard lookup.
- When the DO is evicted mid-fill (rare, but possible on abrupt eviction), the `inflight` map is lost; followers timeout rather than receive the result. Set a reasonable `fetch` timeout on the caller.

## Verification

1. Seed a product into D1, then flush the Cache API with `cache.delete()`.
2. Issue #<number> concurrent requests via `hey -n 100 -c 100 /products/123`.
3. Check D1 query logs — expect exactly **one** `SELECT` per product, not 100.
4. Confirm `source` field in DO responses shows `"leader"` for one and `"coalesced"` for the rest.
5. Issue a second burst after TTL expiry; confirm the pattern repeats cleanly.

## Related

- `request-coalescing-deduplication-edge.md`
- `circuit-breaker-kv-state-machine.md`
- `caching-layers-cloudflare-workers-kv-r2.md`
- `distributed-semaphore-durable-objects.md`
- `write-coalescing-durable-objects-d1.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://en.wikipedia.org/wiki/Cache_stampede
