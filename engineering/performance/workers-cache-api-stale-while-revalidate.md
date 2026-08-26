# Workers Cache API — Stale-While-Revalidate Pattern

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Worker fetches data from an origin or D1 database on every request, adding 50-200 ms of latency. You want cached responses served instantly while fresh data is fetched in the background, so the user never waits for a cache miss penalty.

---

## Context
Cloudflare Workers expose the standard Cache API (`caches.default`). The `stale-while-revalidate` HTTP directive lets you serve a stale cached entry immediately and simultaneously trigger a background refresh using `ctx.waitUntil()`. Because `waitUntil` extends the Worker's lifetime beyond response delivery, the background fetch completes even after the client already received the stale response. Cache key normalization (stripping auth tokens, sorting query params) prevents key explosion. Mutation endpoints must call `cache.delete()` to avoid serving stale state after writes.

---

## Section 1 — Cache-Control Header Config

```toml
# wrangler.toml — no special bindings needed for Cache API
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

# Optional: set default cache TTL at the zone level via Page Rules / Cache Rules
# s-maxage=60            → CDN treats entry as fresh for 60 s
# stale-while-revalidate=300 → serve stale for up to 5 min while revalidating
```

## Section 2 — Implementation

```typescript
import { ExecutionContext } from '@cloudflare/workers-types';

export interface Env {
  ORIGIN_URL: string;
}

/** Strip auth-related params so different users share the same cache entry. */
function normalizeCacheKey(request: Request): Request {
  const url = new URL(request.url);
  url.searchParams.delete('token');
  url.searchParams.delete('api_key');
  // Sort remaining params for canonical ordering
  const sorted = new URLSearchParams(
    [...url.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b))
  );
  url.search = sorted.toString();
  return new Request(url.toString(), { method: 'GET', headers: request.headers });
}

async function fetchAndCache(
  cacheKey: Request,
  originUrl: string,
  cache: Cache
): Promise<Response> {
  const originResponse = await fetch(originUrl + new URL(cacheKey.url).pathname + new URL(cacheKey.url).search);
  if (!originResponse.ok) return originResponse;

  const responseToCache = new Response(originResponse.body, originResponse);
  responseToCache.headers.set(
    'Cache-Control',
    's-maxage=60, stale-while-revalidate=300'
  );
  responseToCache.headers.set('X-Cache-Populated', 'true');

  // Store in cache — fire-and-forget is fine here
  await cache.put(cacheKey, responseToCache.clone());
  return responseToCache;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Only cache GET/HEAD
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return fetch(request);
    }

    const cache = caches.default;
    const cacheKey = normalizeCacheKey(request);
    const cached = await cache.match(cacheKey);

    if (cached) {
      const age = parseInt(cached.headers.get('Age') ?? '0', 10);
      const cc = cached.headers.get('Cache-Control') ?? '';
      const sMaxAge = parseInt(cc.match(/s-maxage=(\d+)/)?.[1] ?? '0', 10);
      const swr = parseInt(cc.match(/stale-while-revalidate=(\d+)/)?.[1] ?? '0', 10);

      if (age <= sMaxAge) {
        // Still fresh — serve directly
        const res = new Response(cached.body, cached);
        res.headers.set('X-Cache', 'HIT-FRESH');
        return res;
      }

      if (age <= sMaxAge + swr) {
        // Stale but within SWR window — serve stale, revalidate in background
        ctx.waitUntil(fetchAndCache(cacheKey, env.ORIGIN_URL, cache));
        const res = new Response(cached.body, cached);
        res.headers.set('X-Cache', 'HIT-STALE');
        return res;
      }
    }

    // Cache miss or expired beyond SWR — fetch synchronously
    const fresh = await fetchAndCache(cacheKey, env.ORIGIN_URL, cache);
    const res = new Response(fresh.body, fresh);
    res.headers.set('X-Cache', 'MISS');
    return res;
  },
};
```

## Section 3 — Cache Purge on Mutation

```typescript
// Purge a specific URL from cache after a write operation
async function purgeCache(url: string): Promise<void> {
  const cache = caches.default;
  const key = normalizeCacheKey(new Request(url));
  const deleted = await cache.delete(key);
  console.log(`Cache purge for ${url}: ${deleted ? 'deleted' : 'not found'}`);
}

// In your mutation handler (POST/PUT/PATCH/DELETE):
export async function handleMutation(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const result = await fetch(request); // proxy to origin
  if (result.ok) {
    // Purge the GET equivalent in background
    const getUrl = request.url.replace('/api/write/', '/api/read/');
    ctx.waitUntil(purgeCache(getUrl));
  }
  return result;
}
```

---

## Anti-patterns
- **Caching POST responses** — POST is not idempotent; only cache GET/HEAD to avoid serving stale mutations.
- **Including auth tokens in cache keys** — leaks user data across requests; always strip credentials from the key.
- **Forgetting `cache.put` requires a `GET` request key** — passing a POST Request object to `cache.put` throws; always construct a synthetic GET key.
- **Infinite SWR windows** — a very large `stale-while-revalidate` value means users can see arbitrarily old data; cap it at 5× the `s-maxage`.

---

## Gotchas
- `caches.default` is scoped to the Cloudflare data centre; entries are not globally replicated on demand — a cache miss in FRA won't be warmed by a hit in LAX.
- The `Age` header is set by Cloudflare automatically when serving from cache; read it to compute real staleness instead of relying on absolute timestamps.
- `cache.delete()` only removes entries from the local PoP — use Cache Purge API for zone-wide invalidation.
- Workers Cache API does not support `Vary` on `Cookie` or `Authorization` headers; normalization is your responsibility.
- `ctx.waitUntil` must be called before the response is returned, not inside an async callback after `return`.

---

## Verification

```bash
# First request — expect MISS
curl -i https://my-worker.example.com/api/data | grep -E 'X-Cache|Age'
# X-Cache: MISS

# Second request within 60 s — expect HIT-FRESH
curl -i https://my-worker.example.com/api/data | grep -E 'X-Cache|Age'
# X-Cache: HIT-FRESH
# Age: 12

# After 61-360 s — expect HIT-STALE + background revalidation
curl -i https://my-worker.example.com/api/data | grep -E 'X-Cache|Age'
# X-Cache: HIT-STALE
# Age: 75

# Confirm revalidation populated fresh entry
sleep 1
curl -i https://my-worker.example.com/api/data | grep -E 'X-Cache|Age'
# X-Cache: HIT-FRESH
# Age: 1
```

---

## Related
- `workers-kv-bulk-read-cache-warming.md`
- `workers-subrequest-parallelism-promise-all.md`
- `workers-early-hints-103-link-preload.md`

---

## Sources
- Cloudflare Cache API docs — https://developers.cloudflare.com/workers/runtime-apis/cache/
- MDN stale-while-revalidate — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control#stale-while-revalidate
- RFC 5861 HTTP Cache-Control Extensions — https://www.rfc-editor.org/rfc/rfc5861
