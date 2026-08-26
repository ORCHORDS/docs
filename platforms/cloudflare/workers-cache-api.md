# workers-cache-api

**Issue:** Use the CF Cache API in Workers — read-through, write-through
**Date:** 2026-08-09
**Status:** documented

## Symptom
You want to cache HTML responses at the edge. You use a
custom cache. The cache works but it's not at the edge; it's
in your Worker. Users in Asia still have high latency.

## Root cause
**The Workers Cache API is at the edge.** Use it; don't
build a custom cache inside the Worker.

**Source:** CF Cache API:
https://developers.cloudflare.com/workers/runtime-apis/cache/

> "The Cache API allows you to store and retrieve network
> requests and responses from Cloudflare's edge network."

## The "read-through" pattern

```ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;

    // 1. Check cache
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }

    // 2. Miss: fetch from origin
    const response = await fetch(request);

    // 3. Cache the response (only if it's 200)
    if (response.status === 200) {
      const cacheable = new Response(response.body, response);
      cacheable.headers.set('Cache-Control', 'public, max-age=300');
      ctx.waitUntil(cache.put(request, cacheable.clone()));
    }

    return response;
  },
};
```

The cache is at the edge; the user gets a cached response
from the closest CF POP.

## The "Cache-Control" header

The Cache API respects `Cache-Control`:
- `public, max-age=N` — cache for N seconds
- `public, max-age=N, immutable` — cache for N seconds, don't
  revalidate
- `public, max-age=N, stale-while-revalidate=M` — serve stale
  for M seconds while refreshing
- `private` — don't cache
- `no-store` — never cache
- `no-cache` — always revalidate

```ts
const cacheable = new Response(response.body, response);
cacheable.headers.set('Cache-Control', 'public, max-age=3600, stale-while-revalidate=86400');
```

## The "Vary" header

For content that varies by request headers:
```ts
const cacheable = new Response(response.body, response);
cacheable.headers.set('Vary', 'Accept-Encoding, Accept-Language');
```

The cache key includes the Vary headers. Two requests with
different `Accept-Language` get different cache entries.

## The "cache key" pattern

The cache key is the `Request` object:
- URL
- Method
- Headers (filtered by Vary)

A POST request is not cached (default). A GET request is.

```ts
// To cache a different URL than the request
const cacheKey = new Request(url, { method: 'GET', headers: { 'Cache-Key': 'home' } });
const cached = await cache.match(cacheKey);
```

## The "purge" pattern

```ts
// Purge by URL
await cache.delete(request);

// Purge by pattern (not directly supported in Cache API; use the CF API)
```

For bulk purge, use the CF API:
```bash
curl -X POST "https://api.cloudflare.com/client/v4/zones/<zone>/purge_cache" \
  -H "Authorization: Bearer <token>" \
  -d '{"files": ["https://example.com/..."]}'
```

## The "conditional request" pattern

For "revalidate" (return 304 if unchanged):
```ts
const ifNoneMatch = request.headers.get('If-None-Match');
const etag = computeETag(response);

if (ifNoneMatch === etag) {
  return new Response(null, { status: 304 });
}

const response = new Response(body, { status: 200, headers: { ETag: etag } });
return response;
```

The browser (or CDN) sends `If-None-Match`; if the ETag
matches, return 304 (not modified).

## The "stale-while-revalidate" pattern

```ts
const cache = caches.default;
const cached = await cache.match(request);

if (cached) {
  // Serve cached; refresh in background
  ctx.waitUntil(refreshCache(request, cache));
  return cached;
}

const response = await fetch(request);
if (response.status === 200) {
  const cacheable = new Response(response.body, response);
  cacheable.headers.set('Cache-Control', 'public, max-age=300, stale-while-revalidate=86400');
  ctx.waitUntil(cache.put(request, cacheable.clone()));
}
return response;

async function refreshCache(request: Request, cache: Cache) {
  const response = await fetch(request);
  if (response.status === 200) {
    const cacheable = new Response(response.body, response);
    cacheable.headers.set('Cache-Control', 'public, max-age=300, stale-while-revalidate=86400');
    await cache.put(request, cacheable);
  }
}
```

The user always gets a fast response; the cache is kept
fresh in the background.

## The "cache + auth" gotcha

**Don't cache authenticated responses by default.** A
cached `/api/me` returns the wrong user's data.

```ts
if (request.headers.get('Authorization')) {
  // Don't cache
  return new Response(null, { headers: { 'Cache-Control': 'no-store' } });
}
```

Or use the `Vary` header to include auth:
```ts
cacheable.headers.set('Vary', 'Authorization');
// The cache key includes Authorization; each user gets their
// own cache entry. But this defeats the purpose of caching.
```

## The "cache + cookie" gotcha

Cookies are request-specific. By default, the Cache API
doesn't include cookies in the cache key. To include:
```ts
const cacheable = new Response(response.body, response);
cacheable.headers.set('Vary', 'Cookie');
```

But again, this defeats the purpose.

## The "size limit" gotcha

The Cache API has a size limit (per cache entry). For large
responses, the cache may not store them:
- 512 MB per entry (CF default)
- 1 GB per request (CF limit)

For most apps, this is enough. For media, store in R2.

## The "Cache API vs KV" choice

| Use case | Use |
|---|---|
| HTML pages | Cache API (CDN) |
| API responses (no user data) | Cache API |
| Per-user data | KV (with user/tenant in key) |
| Aggregations | KV |
| Object data | R2 |

The Cache API is for HTTP responses. KV is for arbitrary
data.

## Verification
- **Test:** `test/cache.test.ts > cache.match returns the
  cached response` — passes
- **Live:** Cache hit rate is monitored (CF Analytics)
- **Audit:** Quarterly review of cache TTLs

## Gotchas
- **The "Cache API is per-isolate" gotcha.** Each Worker
  isolate has its own cache (but they sync). The first
  request after deploy is a miss.
- **The "Cache API doesn't cache POST" gotcha.** By default,
  only GET/HEAD are cached. Use `cache.put` explicitly for
  other methods.
- **The "Cache-Control override" gotcha.** If the origin
  sends `Cache-Control: no-store`, the Cache API doesn't
  cache. Strip the header before caching if you want to
  override.
- **The "cache purge" timing gotcha.** A purge may take a
  few seconds to propagate. Don't rely on instant purge.

## Related
- `cloudflare/kv-eventually-consistent.md`
- `cache-strategies.md`
- `cache-strategies-detail.md`
- `caching-strategies-detail.md`
- `content-delivery-network.md`
- CF Cache API: https://developers.cloudflare.com/workers/runtime-apis/cache/
