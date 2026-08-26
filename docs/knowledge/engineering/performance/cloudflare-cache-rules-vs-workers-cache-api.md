# Cloudflare Cache Rules vs Workers Cache API: Decision Guide

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your team is arguing about whether to add a cache layer in a Worker or to configure it through the Cloudflare dashboard Cache Rules. Responses are not being cached at the edge as expected, or cache hit rates are lower than anticipated. You need a clear mental model of when each mechanism is the right tool.

## Context

Cloudflare exposes two distinct caching control surfaces that operate at different layers of the request pipeline. Cache Rules (formerly Page Rules cache settings) are declarative configuration that Cloudflare's edge evaluates before a Worker runs. The Workers Cache API (`caches.default` / `caches.open()`) is imperative code that executes inside a Worker script. Misunderstanding which layer owns the response leads to cache poisoning, unexpected misses, or configuration that silently overrides the other.

## Cache Rules: Declarative Edge Configuration

Cache Rules evaluate at the Cloudflare WAF/routing layer, before the Worker is invoked. They operate on the raw request and cannot inspect a transformed request or a computed cache key your Worker constructs.

```typescript
// This Worker logic runs AFTER Cache Rules have already made their caching decision.
// Cache Rules that match this request may short-circuit the Worker entirely.
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // By the time we are here, a Cache Rule with "Cache Everything" may have
    // already served a cached response and never reached this Worker.
    // Verify with cf.cacheStatus on the incoming request object:
    const cacheStatus = (request as any).cf?.cacheStatus ?? "UNKNOWN";
    console.log("cf.cacheStatus:", cacheStatus); // HIT | MISS | EXPIRED | BYPASS | DYNAMIC

    return fetch(request);
  },
};
```

Cache Rules are best for:
- HTML pages that need simple TTL overrides without custom logic
- Bypassing cache for authenticated paths (`/account/*`)
- Setting edge TTL independently of the `Cache-Control` origin sends
- Applying cache behaviour to assets served from Pages or R2 without a Worker

## Workers Cache API: Imperative Programmatic Caching

The Cache API lets a Worker store and retrieve `Response` objects using arbitrary cache keys — including keys derived from request body, decoded JWT claims, or normalised query parameters.

```typescript
const CACHE_VERSION = "v3";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;

    // Build a normalised cache key: strip tracking params, canonicalise sort order
    const url = new URL(request.url);
    url.searchParams.delete("utm_source");
    url.searchParams.delete("utm_medium");
    url.searchParams.sort();
    const cacheKey = new Request(`${url.toString()}?_cv=${CACHE_VERSION}`, {
      method: "GET",
      headers: { "Accept-Encoding": request.headers.get("Accept-Encoding") ?? "" },
    });

    const cached = await cache.match(cacheKey);
    if (cached) {
      return new Response(cached.body, {
        status: cached.status,
        headers: {
          ...Object.fromEntries(cached.headers),
          "X-Cache": "HIT",
        },
      });
    }

    const origin = await fetch(request);
    if (origin.ok) {
      const toCache = new Response(origin.clone().body, {
        status: origin.status,
        headers: {
          ...Object.fromEntries(origin.headers),
          "Cache-Control": "public, max-age=300, s-maxage=3600",
        },
      });
      ctx.waitUntil(cache.put(cacheKey, toCache));
    }

    return new Response(origin.body, {
      status: origin.status,
      headers: {
        ...Object.fromEntries(origin.headers),
        "X-Cache": "MISS",
      },
    });
  },
};
```

## Choosing Between Them: Decision Matrix

```typescript
// Pseudo-decision logic — use as a planning aid, not runtime code

type CachingNeed =
  | "simple-ttl-override"        // → Cache Rules only
  | "bypass-authenticated"       // → Cache Rules only
  | "custom-cache-key"           // → Workers Cache API
  | "body-dependent-key"         // → Workers Cache API
  | "stale-while-revalidate-custom" // → Workers Cache API + waitUntil
  | "vary-on-cookie-value"       // → Workers Cache API (Cache Rules can only vary on presence)
  | "surrogate-key-purge"        // → Cache Rules + Cloudflare-Cache-Tag header
  | "multi-tenant-namespace"     // → Workers Cache API with caches.open('tenant-id')

function pickMechanism(need: CachingNeed): string {
  const map: Record<CachingNeed, string> = {
    "simple-ttl-override":          "Cache Rules — zero Worker CPU cost",
    "bypass-authenticated":         "Cache Rules — evaluated before Worker billing begins",
    "custom-cache-key":             "Workers Cache API — full control over key",
    "body-dependent-key":           "Workers Cache API — read body then hash",
    "stale-while-revalidate-custom":"Workers Cache API — ctx.waitUntil revalidation",
    "vary-on-cookie-value":         "Workers Cache API — decode and normalise cookie",
    "surrogate-key-purge":          "Cache Rules + Cloudflare-Cache-Tag on origin responses",
    "multi-tenant-namespace":       "Workers Cache API — caches.open() per tenant",
  };
  return map[need];
}
```

## Interaction Order and Pitfalls

```typescript
// Checklist as executable comments

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // 1. Cache Rules fire BEFORE this Worker — a "Cache Everything" rule at /static/*
    //    means this code never runs for those paths. Test with `wrangler tail`.

    // 2. If a Cache Rule sets Edge TTL but the Worker rewrites the response,
    //    the rewritten response resets the edge TTL — use `cf.cacheTtl` in fetch options
    //    to re-assert TTL from inside the Worker.
    const response = await fetch(request, {
      cf: {
        cacheTtl: 3600,
        cacheEverything: true,
        cacheKey: request.url + "|" + (request.headers.get("CF-IPCountry") ?? "XX"),
      },
    });

    // 3. caches.default.put() stores a SECOND copy independent of the Cloudflare
    //    shared cache used by Cache Rules. They do NOT share storage.
    //    Treat them as two separate namespaces.

    return response;
  },
};
```

## Anti-patterns

- Setting long `Edge TTL` in Cache Rules AND calling `cache.put()` with short TTLs in a Worker — the Cache Rule may serve stale data that bypasses Worker logic entirely.
- Using `caches.default.put()` for personalised responses keyed only on URL — include a user-specific token fragment to prevent cross-user cache poisoning.
- Relying on Cache Rules to vary on cookie value — Cache Rules can only bypass/pass-through based on cookie presence, not value. Use the Workers Cache API for value-based variation.

## Gotchas

- `cache.match()` returns `undefined` (not a `Response` with 404) on a miss — always guard the return value before calling `.body` or `.headers`.
- Workers served from a route with `workers.dev` domain bypass Cloudflare Cache Rules — Cache Rules apply only to proxied zones (orange-cloud DNS).

## Verification

```bash
# Confirm cache status from the edge
curl -sI "https://example.com/api/products" | grep -i "cf-cache-status\|x-cache"

# Tail Worker logs to see cache hit/miss from Cache API
wrangler tail --format pretty --filter "X-Cache"

# Use Cloudflare Cache Purge API to clear Cache API entries
curl -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/purge_cache" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"files":["https://example.com/api/products"]}'
```

## Related

- `performance/cdn-cache-strategy.md`
- `performance/cache-control-headers.md`
- `performance/cache-stampede-prevention.md`
- `performance/workers-cold-start-optimization.md`

## Sources

- https://developers.cloudflare.com/cache/how-to/cache-rules/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/cache/concepts/cache-status/
