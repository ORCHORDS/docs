# Advanced Cache API Patterns with Custom Cache Keys in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker fetches data from an origin or runs expensive computation. Default cache keys (the full URL) either over-cache (serving stale data when only query params differ) or under-cache (cache misses because tracking params like `utm_source` pollute the key). You need precise, deterministic cache keys that maximise hit rate while guaranteeing correctness.

## Context

The Cache API (`caches.default`) in Workers gives you direct, programmatic control over what goes into the cache and under what key. Unlike the automatic HTTP cache, you construct a synthetic `Request` object whose URL acts as the cache key. This lets you strip irrelevant parameters, normalise headers, and embed version signals — all before the lookup happens.

Key facts:
- Cache API is available in all Workers plans.
- `caches.default` is the same cache the Cloudflare HTTP cache uses; writes from Workers are visible to the edge cache and vice-versa.
- The cache key is the full URL of the `Request` passed to `cache.match()` / `cache.put()`.
- `cache.put()` requires a `Response` with a valid `Cache-Control` or `Expires` header; without one the response is not stored.
- `waitUntil()` lets you write to the cache after the response has been sent to the client, eliminating added latency.

## Custom Cache Key Construction

```typescript
import { VERSION_HASH } from './version'; // e.g. git short-SHA injected at build time

const CACHE_PARAMS = ['q', 'lang', 'page', 'per_page'] as const;
const CACHE_HEADERS = ['accept'] as const;

/**
 * Build a deterministic cache key from:
 *  - origin + pathname
 *  - a whitelist of query params (sorted for stability)
 *  - selected request headers that affect the response shape
 *  - a build-time version hash for cache-busting on deploy
 */
function buildCacheKey(request: Request): Request {
  const url = new URL(request.url);

  // 1. Keep only the params that actually influence the response.
  const kept = new URLSearchParams();
  for (const key of CACHE_PARAMS) {
    const val = url.searchParams.get(key);
    if (val !== null) kept.set(key, val);
  }

  // 2. Fold in vary-critical request headers.
  for (const header of CACHE_HEADERS) {
    const val = request.headers.get(header);
    if (val) kept.set(`_h_${header}`, val.split(',')[0].trim()); // normalise Accept
  }

  // 3. Append version hash so a new deploy auto-busts stale entries.
  kept.set('_v', VERSION_HASH);

  // 4. Sort for determinism regardless of original param order.
  kept.sort();

  url.search = kept.toString();

  // Return a GET Request — cache.put() only accepts GET.
  return new Request(url.toString(), { method: 'GET' });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;
    const cacheKey = buildCacheKey(request);

    // --- Cache read ---
    const cached = await cache.match(cacheKey);
    if (cached) {
      const hit = new Response(cached.body, cached);
      hit.headers.set('X-Cache', 'HIT');
      return hit;
    }

    // --- Origin fetch ---
    const originResponse = await fetch(request);

    if (!originResponse.ok) return originResponse;

    // Clone before consuming — body can only be read once.
    const responseToCache = new Response(originResponse.body, originResponse);

    // 5. Set s-maxage to control edge TTL independently of the browser TTL.
    responseToCache.headers.set(
      'Cache-Control',
      'public, max-age=60, s-maxage=300, stale-while-revalidate=60'
    );
    responseToCache.headers.set('X-Cache', 'MISS');

    // 6. Non-blocking write — response is already on the wire to the client.
    ctx.waitUntil(cache.put(cacheKey, responseToCache.clone()));

    return responseToCache;
  },
};
```

## Controlling TTL with `s-maxage`

`s-maxage` is the directive that governs Cloudflare's shared cache; `max-age` governs the browser. Setting them independently lets you:

- Keep the browser cache short (e.g. 60 s) so users see fresh content on reload.
- Keep the edge cache long (e.g. 300 s) to absorb traffic spikes without hammering the origin.
- Add `stale-while-revalidate` so Cloudflare serves the stale copy while asynchronously revalidating in the background.

If the upstream response already sets `Cache-Control`, override it on the `responseToCache` copy only — the original response sent to the client can keep its own headers.

## Cache-Busting with a Version Hash

Embedding `_v=<git-sha>` in the cache key means every deploy automatically invalidates all cached entries without needing an explicit purge API call. The `VERSION_HASH` constant is injected at build time via Wrangler's `[vars]` or via a build step that writes `src/version.ts`:

```toml
# wrangler.toml
[vars]
VERSION_HASH = "abc1234"  # overwritten by CI: wrangler deploy --var VERSION_HASH:$(git rev-parse --short HEAD)
```

## `waitUntil` for Non-Blocking Writes

`ctx.waitUntil(promise)` extends the Worker's lifetime beyond the response send. Without it, the isolate may be torn down before `cache.put()` completes, silently dropping the write. Always wrap cache population in `waitUntil` when the response has already been returned:

```typescript
ctx.waitUntil(cache.put(cacheKey, responseToCache.clone()));
// ^ clone() is required because put() consumes the body
```

## Anti-patterns

- **Using the raw `request.url` as the cache key** when tracking params (`utm_*`, `fbclid`) are present — each unique URL becomes a separate cache entry, exploding cardinality and effectively disabling caching.
- **Forgetting to clone** before `cache.put()` — the body stream is consumed and subsequent reads return empty.
- **Omitting `Cache-Control`** on the response passed to `cache.put()` — the Cache API will refuse to store it.
- **Varying on the full `Accept` header** without normalisation — minor whitespace differences produce different keys.

## Gotchas

- `cache.match()` performs an exact URL match; it does **not** respect `Vary` headers the way an HTTP cache does. You must encode vary dimensions into the key manually (as shown with `_h_accept` above).
- Cache API writes are **eventually consistent** across PoPs. A request hitting a different PoP immediately after a `put()` may still miss.
- The Cache API is **not available in local `wrangler dev`** (it's a no-op). Use `wrangler dev --remote` to test caching behaviour against real Cloudflare infrastructure.
- Per-request cache storage is limited; very large responses (> 512 MB) cannot be stored via the Cache API.

## Verification

```bash
# Check cache status via response header
curl -si https://example.com/api/search?q=hello | grep -E 'X-Cache|CF-Cache-Status|Cache-Control'

# Confirm tracking param is stripped — both URLs should return the same cached response
curl -si "https://example.com/api/search?q=hello&utm_source=newsletter" | grep X-Cache
curl -si "https://example.com/api/search?q=hello" | grep X-Cache
```

Expect `X-Cache: HIT` on the second request if the first populated the cache.

## Related

- `cloudflare-tiered-cache-workers-origin-shield.md`
- `workers-ai-inference-result-caching-kv.md`
- [Cache API — Cloudflare Docs](https://developers.cloudflare.com/workers/runtime-apis/cache/)

## Sources

- Cloudflare Workers Cache API reference (2025)
- Cloudflare Cache-Control directive documentation
- Cloudflare `waitUntil` lifecycle documentation
