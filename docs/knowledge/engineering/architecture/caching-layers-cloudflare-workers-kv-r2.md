# Four-Tier Cache Topology on Cloudflare Workers, KV, and R2

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project feed endpoints show D1 latency spikes of 150–300 ms at burst read peaks despite low query complexity. D1's per-database throughput ceiling is hit before query execution time becomes the bottleneck. Simultaneously, mobile clients on 4G connections experience ~800 ms TTFB because large JSON payloads are re-fetched on every pull-to-refresh even when content has not changed.

## Context

A four-tier cache topology isolates D1 from read traffic at every layer. Each tier has a distinct latency profile, TTL strategy, and invalidation mechanism. Mobile cache keys are split by device tier to allow device-appropriate TTLs and payload shapes without duplicating business logic in downstream Workers.

## Cache Tier Overview

```
Request
  │
  ▼
[L0] Cloudflare CDN edge cache ─── Cache-Control response headers
  │ miss
  ▼
[L1] Workers Cache API (request-scoped, per PoP) ─── cache.put() / cache.match()
  │ miss
  ▼
[L2] Workers KV ─── get() / put() with TTL
  │ miss
  ▼
[L3] R2 (full projection JSON) ─── getObject() / putObject()
  │ miss
  ▼
[L4] D1 (authoritative) ─── SQL query, then back-fill L3 → L2 → L1
```

Typical latency at each tier:

| Tier | Technology        | Hit latency  | TTL range       | Invalidation mechanism         |
|------|-------------------|-------------|-----------------|-------------------------------|
| L0   | CDN edge cache    | < 5 ms      | 15 s – 120 s    | Purge by tag / URL             |
| L1   | Cache API         | 5 – 15 ms   | 30 s – 300 s    | `cache.delete()` in Worker     |
| L2   | KV                | 10 – 50 ms  | 30 s – 3 600 s  | `kv.delete()` or TTL expiry    |
| L3   | R2                | 30 – 120 ms | No TTL (eternal)| `r2.delete()` after rebuild    |
| L4   | D1                | 50 – 300 ms | N/A             | Source of truth                |

## TTL Strategy per Resource Type

| Resource              | L0 (CDN) | L1 (Cache API) | L2 (KV)  | L3 (R2)  |
|-----------------------|----------|----------------|----------|----------|
| Anonymous feed        | 15 s     | 30 s           | 60 s     | eternal  |
| Post detail           | 30 s     | 60 s           | 300 s    | eternal  |
| Reaction counts       | 5 s      | 10 s           | 30 s     | eternal  |
| Profile stats         | 60 s     | 120 s          | 600 s    | eternal  |
| Search results        | 0 (no)   | 0 (no)         | 15 s     | no       |
| Media thumbnails      | 3 600 s  | 86 400 s       | eternal  | eternal  |

## Mobile Cache Key Device-Type Splitting

The Cache API key is built from the URL plus a device-tier suffix. This prevents a desktop-shaped response from being served to a mobile client and allows different TTLs per tier.

```typescript
// src/cache/cacheKey.ts
export function buildCacheKey(request: Request, tier: 'mobile' | 'desktop'): Request {
  const url = new URL(request.url);
  url.searchParams.set('_tier', tier); // suffix for cache key differentiation
  return new Request(url.toString(), { method: 'GET' });
}
```

```typescript
// src/handlers/feed.ts
import { buildCacheKey } from '../cache/cacheKey';

export async function handleFeed(request: Request, env: Env): Promise<Response> {
  const tier = (request.headers.get('X-Client-Tier') ?? 'desktop') as 'mobile' | 'desktop';
  const cacheKey = buildCacheKey(request, tier);
  const cache = caches.default;
  const ttlMobile = 45;   // seconds
  const ttlDesktop = 15;

  // L1: Cache API
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  // L2: KV
  const kvKey = `feed:${tier}:latest`;
  const kvRaw = await env.KV.get(kvKey, 'text');
  if (kvRaw) {
    const resp = new Response(kvRaw, {
      headers: buildCacheHeaders(tier === 'mobile' ? ttlMobile : ttlDesktop),
    });
    env.CTX.waitUntil(cache.put(cacheKey, resp.clone()));
    return resp;
  }

  // L3: R2
  const r2Obj = await env.FEED_BUCKET.get(`projections/feed-${tier}.json`);
  if (r2Obj) {
    const text = await r2Obj.text();
    const resp = new Response(text, {
      headers: buildCacheHeaders(tier === 'mobile' ? ttlMobile : ttlDesktop),
    });
    env.CTX.waitUntil(Promise.all([
      env.KV.put(kvKey, text, { expirationTtl: tier === 'mobile' ? ttlMobile : ttlDesktop }),
      cache.put(cacheKey, resp.clone()),
    ]));
    return resp;
  }

  // L4: D1 fallback
  const { results } = await env.DB.prepare(
    `SELECT id, body_preview, reaction_count, created_at FROM posts
     ORDER BY created_at DESC LIMIT ?`
  ).bind(tier === 'mobile' ? 20 : 50).all();

  const payload = JSON.stringify({ items: results, tier });
  const resp = new Response(payload, {
    headers: buildCacheHeaders(tier === 'mobile' ? ttlMobile : ttlDesktop),
  });

  // Back-fill all tiers
  env.CTX.waitUntil(Promise.all([
    env.FEED_BUCKET.put(`projections/feed-${tier}.json`, payload),
    env.KV.put(kvKey, payload, { expirationTtl: tier === 'mobile' ? ttlMobile : ttlDesktop }),
    cache.put(cacheKey, resp.clone()),
  ]));

  return resp;
}

function buildCacheHeaders(maxAge: number): Headers {
  return new Headers({
    'Content-Type': 'application/json',
    'Cache-Control': `public, max-age=${maxAge}, stale-while-revalidate=${maxAge * 3}`,
  });
}
```

## Stale-While-Revalidate Semantics

`stale-while-revalidate` instructs the CDN (L0) and browsers to serve a stale response immediately while fetching a fresh one in the background. On example project this is critical for mobile: a 4G client on a congested network gets sub-50 ms first-byte from stale CDN cache while the Worker revalidates asynchronously.

```
Client request
      │
      ├── CDN: within max-age ────► serve immediately (fresh)
      ├── CDN: max-age expired, within s-w-r window ────► serve stale + revalidate in background
      └── CDN: beyond s-w-r window ────► block, fetch from origin
```

Configured per resource type in `buildCacheHeaders`: `max-age=15, stale-while-revalidate=45` means clients accept up to 60 seconds of staleness maximum before a blocking fetch.

## Cache Invalidation on Write

When a post is created or a reaction toggles, the Queue consumer (projection builder) must purge affected cache tiers before writing new projections.

```typescript
// projection-worker: invalidation before back-fill
async function invalidateFeedCache(env: Env): Promise<void> {
  await Promise.all([
    env.KV.delete('feed:mobile:latest'),
    env.KV.delete('feed:desktop:latest'),
    env.FEED_BUCKET.delete('projections/feed-mobile.json'),
    env.FEED_BUCKET.delete('projections/feed-desktop.json'),
  ]);
  // L0 CDN: use Cloudflare Cache API purge via REST if needed
  // L1 Cache API: per-PoP; Worker-side delete is best-effort across PoPs
}
```

Note: `caches.default.delete()` only purges the calling PoP's in-memory cache. For global L1 purge, use the Cloudflare REST API `purge_cache` endpoint via `waitUntil`.

## Anti-patterns

- **Writing D1 rows and immediately reading them from a cached feed** — the cache will serve stale data; write events must invalidate relevant cache keys before the client re-polls.
- **Using KV as L1 (primary cache) for sub-second freshness** — KV has 10–50 ms read latency and 60-second eventual consistency lag on writes; the Cache API is faster for sub-30-second TTLs.
- **Storing full media objects in KV** — KV value size limit is 25 MB but performance degrades above 1 MB; store media in R2 and cache metadata in KV.
- **Identical cache keys for mobile and desktop** — desktop responses are 3–5× larger; mobile clients cache-warm the desktop tier and vice versa without key splitting.
- **Infinite R2 projection accumulation** — delete old projection objects after successful rebuild to avoid paying for stale data indefinitely.

## Gotchas

- `caches.default` is request-scoped per isolate invocation; cache entries written in one request are available to subsequent requests at the same PoP but not guaranteed globally.
- KV `expirationTtl` rounds up to the nearest second; values below 60 seconds are rejected on the free plan.
- R2 `get()` returns `null` (not a 404 Response) when the key does not exist; always null-check before calling `.text()`.
- `Cache-Control: no-store` on any response in the chain prevents all downstream caching including the browser; reserve it for auth responses only.
- Cloudflare CDN does not cache responses with cookies set unless `cf: { cachEverything: true }` is configured in the Worker; example project anonymous tokens should travel in the `Authorization` header, not cookies, to keep feed responses CDN-cacheable.

## Verification

```bash
# Confirm CDN cache hit (L0)
curl -sI https://api.example.com/feed | grep -i 'cf-cache-status'
# Expect: CF-Cache-Status: HIT  (after first request populates CDN)

# Confirm KV key written
wrangler kv key get --namespace-id=<NS_ID> "feed:mobile:latest" | head -c 200

# Confirm R2 object written
wrangler r2 object get example project-feed-bucket "projections/feed-mobile.json" --file /tmp/proj.json
cat /tmp/proj.json | jq '.items | length'
# Expect: 20 (mobile limit)

# Measure cache hit vs D1 latency
time curl -s https://api.example.com/feed -H "X-Client-Tier: mobile" > /dev/null
# Hit:  < 50 ms
# Miss: 150–350 ms
```

## Related

- `cqrs-cloudflare-workers-d1.md`
- `cdn-architecture.md`
- `distributed-caching.md`
- `cache-aside-pattern.md`
- `read-through-cache.md`
- `feature-flag-cloudflare-workers-kv.md`

## Sources

- Cloudflare Cache API documentation — `caches.default`, TTL behaviour, PoP scoping
- Cloudflare KV documentation — consistency model, size limits
- Cloudflare R2 documentation — object storage, `get()` null semantics
- RFC 5861 — HTTP Cache-Control Extensions for Stale Content (`stale-while-revalidate`)
