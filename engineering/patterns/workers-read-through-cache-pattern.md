# Read-Through Cache Pattern with Cache API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

An origin API is slow, expensive, or rate-limited. You want to serve cached responses at the Cloudflare edge with minimal latency, but the built-in `fetch` cache is opaque. You need control over TTL per content type, stale-while-revalidate behavior, negative caching for 404 responses, cache key normalization, and the ability to purge entries by tag via the Cloudflare Cache Purge API.

---

## Context

The Workers [Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/) (`caches.default`) gives you a `caches.open()`-style interface backed by Cloudflare's CDN. Unlike the `cf` fetch option, you control what gets stored and for how long by constructing `Response` objects with explicit `Cache-Control` headers before calling `cache.put()`.

Stale-while-revalidate is implemented by registering a background `waitUntil` task that re-fetches the origin and calls `cache.put()` again after serving the stale response. Cache purge by tag requires a REST call to the Cloudflare Cache Purge API using an Account API token.

---

## Solution

```typescript
// src/cache-worker.ts

export interface Env {
  ORIGIN_URL: string;              // e.g. "https://api.example.com"
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;            // Cache Purge permission
  CF_ZONE_ID: string;
}

type ContentType = 'json' | 'html' | 'image' | 'font' | 'other';

interface TtlConfig {
  ttl: number;           // seconds — stored in Cache-Control max-age
  swr: number;           // stale-while-revalidate seconds
  negative: number;      // TTL for 404 responses
}

const TTL_MAP: Record<ContentType, TtlConfig> = {
  json:  { ttl: 60,    swr: 30,   negative: 10  },
  html:  { ttl: 300,   swr: 60,   negative: 5   },
  image: { ttl: 86400, swr: 3600, negative: 60  },
  font:  { ttl: 604800, swr: 0,   negative: 60  },
  other: { ttl: 120,   swr: 30,   negative: 10  },
};

function detectContentType(response: Response): ContentType {
  const ct = response.headers.get('Content-Type') ?? '';
  if (ct.includes('json')) return 'json';
  if (ct.includes('html')) return 'html';
  if (ct.includes('image')) return 'image';
  if (ct.includes('font') || ct.includes('woff')) return 'font';
  return 'other';
}

/**
 * Normalize a cache key:
 * - Strip irrelevant query params (e.g. tracking pixels, analytics)
 * - Lower-case the hostname
 * - Sort remaining query params for canonical ordering
 */
function normalizeCacheKey(request: Request): Request {
  const url = new URL(request.url);
  url.hostname = url.hostname.toLowerCase();

  // Remove params that do not affect content
  const DROP_PARAMS = ['utm_source', 'utm_medium', 'utm_campaign', 'fbclid', '_'];
  DROP_PARAMS.forEach((p) => url.searchParams.delete(p));

  // Sort remaining params so ?b=2&a=1 and ?a=1&b=2 hit the same key
  const sorted = new URLSearchParams(
    [...url.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b)),
  );
  url.search = sorted.toString();

  return new Request(url.toString(), {
    method: request.method,
    headers: request.headers,
  });
}

async function fetchFromOrigin(request: Request, env: Env): Promise<Response> {
  const originUrl = new URL(request.url);
  originUrl.hostname = new URL(env.ORIGIN_URL).hostname;
  originUrl.protocol = 'https:';
  return fetch(originUrl.toString(), {
    method: request.method,
    headers: request.headers,
    body: request.method !== 'GET' && request.method !== 'HEAD' ? request.body : undefined,
  });
}

function buildCacheableResponse(originResponse: Response, config: TtlConfig): Response {
  const headers = new Headers(originResponse.headers);

  // Build Cache-Control with stale-while-revalidate
  let cacheControl = `public, max-age=${config.ttl}`;
  if (config.swr > 0) {
    cacheControl += `, stale-while-revalidate=${config.swr}`;
  }
  headers.set('Cache-Control', cacheControl);

  // Tag for purge-by-tag — real tags come from your origin or routing logic
  const pathname = new URL(originResponse.url).pathname;
  const tag = pathname.split('/')[1] ?? 'root'; // e.g. "products", "articles"
  headers.set('Cache-Tag', tag);

  return new Response(originResponse.body, {
    status: originResponse.status,
    statusText: originResponse.statusText,
    headers,
  });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Only cache GET and HEAD
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return fetchFromOrigin(request, env);
    }

    const cacheKey = normalizeCacheKey(request);
    const cache = caches.default;

    const cached = await cache.match(cacheKey);

    if (cached) {
      const age = cached.headers.get('Age') ?? '0';
      const maxAge = parseCacheControl(cached.headers.get('Cache-Control') ?? '').maxAge ?? 0;
      const swr = parseCacheControl(cached.headers.get('Cache-Control') ?? '').swr ?? 0;
      const isStale = Number(age) > maxAge;

      console.log(JSON.stringify({
        event: 'cache_hit',
        url: cacheKey.url,
        age,
        stale: isStale,
      }));

      if (isStale && swr > 0 && Number(age) <= maxAge + swr) {
        // Serve stale while revalidating in the background
        ctx.waitUntil(revalidate(cacheKey, cache, env));
      }

      const response = new Response(cached.body, cached);
      response.headers.set('X-Cache', isStale ? 'STALE' : 'HIT');
      return response;
    }

    console.log(JSON.stringify({ event: 'cache_miss', url: cacheKey.url }));

    const originResponse = await fetchFromOrigin(request, env);
    const contentType = detectContentType(originResponse);
    const config = TTL_MAP[contentType];

    // Negative caching: cache 404s with a short TTL to protect the origin
    if (originResponse.status === 404) {
      const negativeResponse = buildNegativeCacheResponse(originResponse, config);
      ctx.waitUntil(cache.put(cacheKey, negativeResponse.clone()));
      const r = new Response(negativeResponse.body, negativeResponse);
      r.headers.set('X-Cache', 'MISS');
      return r;
    }

    if (originResponse.ok) {
      const cacheable = buildCacheableResponse(originResponse.clone(), config);
      ctx.waitUntil(cache.put(cacheKey, cacheable.clone()));
      cacheable.headers.set('X-Cache', 'MISS');
      return cacheable;
    }

    // Do not cache 5xx errors
    return originResponse;
  },
};

async function revalidate(
  cacheKey: Request,
  cache: Cache,
  env: Env,
): Promise<void> {
  try {
    const fresh = await fetchFromOrigin(cacheKey, env);
    if (fresh.ok) {
      const contentType = detectContentType(fresh);
      const config = TTL_MAP[contentType];
      const cacheable = buildCacheableResponse(fresh, config);
      await cache.put(cacheKey, cacheable);
      console.log(JSON.stringify({ event: 'cache_revalidated', url: cacheKey.url }));
    }
  } catch (err) {
    console.error(JSON.stringify({ event: 'revalidation_failed', url: cacheKey.url, error: String(err) }));
  }
}

function buildNegativeCacheResponse(originResponse: Response, config: TtlConfig): Response {
  const headers = new Headers(originResponse.headers);
  headers.set('Cache-Control', `public, max-age=${config.negative}`);
  return new Response(originResponse.body, {
    status: 404,
    statusText: 'Not Found',
    headers,
  });
}

function parseCacheControl(header: string): { maxAge?: number; swr?: number } {
  const parts = header.split(',').map((s) => s.trim());
  const result: { maxAge?: number; swr?: number } = {};
  for (const part of parts) {
    const [key, value] = part.split('=').map((s) => s.trim());
    if (key === 'max-age') result.maxAge = Number(value);
    if (key === 'stale-while-revalidate') result.swr = Number(value);
  }
  return result;
}

// --- Cache Purge by Tag ---

export async function purgeByTag(tag: string, env: Env): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/purge_cache`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ tags: [tag] }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Cache purge failed: ${response.status} ${body}`);
  }

  console.log(JSON.stringify({ event: 'cache_purged', tag }));
}
```

---

## Implementation Details

**Cache key normalization** removes tracking parameters and sorts query strings so that `?a=1&b=2` and `?b=2&a=1` resolve to the same cache entry. Without normalization, every permutation of equivalent URLs becomes a separate cache miss.

**Stale-while-revalidate** is implemented manually because the Cache API respects `Cache-Control` headers but does not expose an SWR callback. The pattern is: detect staleness by comparing `Age` to `max-age`, then call `ctx.waitUntil(revalidate(...))` to refresh the cache in the background while returning the stale response immediately.

**Negative caching** stores 404 responses with a short TTL (`config.negative`). This prevents cache-miss storms when clients request non-existent resources in a tight loop. The `X-Cache: MISS` header signals that the 404 came from the origin.

**Cache-Tag** is a Cloudflare-specific response header that groups related cache entries. You can purge all entries for a tag with a single API call rather than listing individual URLs.

**TTL strategy** varies by content type: fonts are immutable and cached for a week; JSON API responses are short-lived to allow updates. Adjust `TTL_MAP` to your SLA and origin update frequency.

---

## Anti-patterns

- **Caching `POST` responses.** POST is not idempotent; caching its response violates HTTP semantics and can serve stale mutation results.
- **Using `request.url` directly as the cache key.** Without normalization, tracking parameters create cache fragmentation — every marketing campaign URL becomes a separate entry.
- **Setting a long negative TTL.** A 404 today may be a valid resource tomorrow (e.g. a product that has just been created). Keep `negative` TTLs to 5–60 seconds.
- **Caching 5xx errors.** A server error is transient; caching it turns a momentary outage into a prolonged one from the client's perspective.

---

## Gotchas

- **`cache.put()` and `cache.match()` are zone-scoped.** In local `wrangler dev`, the Cache API writes to a local in-memory store — entries do not persist across restarts and do not reflect production CDN behavior.
- **`Age` header accuracy.** Cloudflare populates `Age` automatically. Do not set it yourself — it will be overwritten with the correct value when served from the edge.
- **Cache-Tag purge requires a paid Cloudflare plan.** The `tags` field in the purge API is only available on Pro plans and above.
- **`waitUntil` has a 30-second wall-clock limit.** If revalidation takes longer than 30 s (unlikely for a fast origin), it will be terminated silently.

---

## Verification

```bash
# First request: MISS
curl -si https://your-worker.workers.dev/api/products/123 | grep -i 'x-cache\|age\|cache-control'

# Second request: HIT
curl -si https://your-worker.workers.dev/api/products/123 | grep -i 'x-cache\|age\|cache-control'

# Purge by tag
curl -X POST https://your-worker.workers.dev/admin/purge \
  -H 'Content-Type: application/json' \
  -d '{"tag": "products"}'

# After purge, next request should be MISS again
curl -si https://your-worker.workers.dev/api/products/123 | grep 'x-cache'
```

---

## Related

- `workers-token-bucket-rate-limiter.md` — protect the origin before reaching the cache
- `workers-inbox-outbox-pattern.md` — invalidate cache entries via outbox events on data change
- Cloudflare Docs: [Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/)
- Cloudflare Docs: [Purge cache by tag](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-cache-tag/)

---

## Sources

- MDN Web Docs — Cache API: https://developer.mozilla.org/en-US/docs/Web/API/Cache
- RFC 5861 — stale-while-revalidate: https://datatracker.ietf.org/doc/html/rfc5861
- Cloudflare Cache API docs: https://developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare Cache-Tag purge: https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-cache-tag/
