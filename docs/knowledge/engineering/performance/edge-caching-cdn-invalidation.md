# Edge Caching and CDN Cache Invalidation

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application serves every request from the origin server, resulting
in high latency for geographically distant users and unnecessary load on
your infrastructure. When you do use a CDN, stale content persists after
updates because cache invalidation is manual and unreliable. Deploying a
content change requires waiting minutes for caches to expire, or you
set TTLs so short that the CDN provides minimal benefit.

## Context

Edge caching stores copies of your content at CDN Points of Presence
(PoPs) worldwide, serving requests from the nearest edge location
instead of the origin server. In 2026, CDN caching has evolved from
simple static file caching to a programmable layer — edge compute (Cloudflare
Workers, Vercel Edge Functions, Fastly Compute) runs cache-decision logic
at the edge, dynamically determining what to cache, how to transform cached
responses, and when to revalidate. Sub-second tag-based invalidation
(Fastly Surrogate-Key, Cloudflare Cache Tags) enables instant purges
without waiting for TTL expiration.

## Cache-Control headers

```
Cache-Control: public, max-age=31536000, immutable
│               │                        │
│               │                        └─ Never revalidate (hashed assets)
│               └─ Cache for 1 year
└─ Any cache (CDN, browser) may store this
```

### Key directives

| Directive | Meaning | Use case |
|---|---|---|
| `public` | Any cache may store | Static assets, public pages |
| `private` | Only browser may store | User-specific data |
| `max-age=N` | Cache for N seconds | All cacheable content |
| `s-maxage=N` | CDN cache for N seconds (overrides max-age for CDN) | Different TTL for CDN vs browser |
| `no-cache` | Must revalidate before serving | Dynamic pages that change often |
| `no-store` | Never cache | Sensitive data, authenticated responses |
| `immutable` | Never revalidate during max-age | Hashed static assets |
| `stale-while-revalidate=N` | Serve stale for N seconds while fetching fresh | Near-instant responses during refresh |
| `stale-if-error=N` | Serve stale for N seconds if origin errors | Resilience during origin outages |

### Recommended patterns

```
# Hashed static assets (bundle.a1b2c3.js)
Cache-Control: public, max-age=31536000, immutable

# HTML pages
Cache-Control: public, max-age=0, s-maxage=60, stale-while-revalidate=300

# API responses (public, cacheable)
Cache-Control: public, s-maxage=30, stale-while-revalidate=60

# API responses (user-specific)
Cache-Control: private, no-cache

# Sensitive data
Cache-Control: private, no-store
```

## Cache invalidation strategies

### 1. Versioned URLs (best practice)

```
/assets/main.a1b2c3d4.js  → Cache forever (immutable)
/assets/main.e5f6g7h8.js  → New version, new URL, new cache entry
```

No invalidation needed — the old URL is never requested again. Build
tools (Webpack, Vite, esbuild) generate hashed filenames automatically.

### 2. Tag-based purging

```http
# Origin response includes cache tag
Surrogate-Key: product-123 category-shoes  (Fastly)
Cache-Tag: product-123, category-shoes     (Cloudflare)

# Purge all content tagged with "product-123"
POST /purge/tag/product-123
→ All edge locations purge matching content in < 200ms
```

Tag-based purging is the best strategy for dynamic content — one API
call purges all pages that reference a changed entity without listing
every URL.

### 3. Path-based purging

```bash
# Purge a specific URL
curl -X POST "https://api.cloudflare.com/..." \
  -d '{"files": ["https://example.com/products/123"]}'

# Purge by path prefix
curl -X POST "https://api.fastly.com/..." \
  -d '{"surrogate_key": "/products/*"}'
```

### 4. Stale-while-revalidate

```
Cache-Control: public, max-age=60, stale-while-revalidate=3600

Timeline:
  0-60s:   Serve from cache (fresh)
  60-3660s: Serve stale immediately, fetch fresh in background
  3660s+:  Must revalidate before serving
```

The user always gets an instant response. Background revalidation
ensures fresh content within seconds without blocking the request.

## Edge compute cache patterns

```typescript
// Cloudflare Worker: programmable cache logic
export default {
  async fetch(request, env) {
    const cache = caches.default;
    const cacheKey = new Request(request.url, request);

    let response = await cache.match(cacheKey);
    if (response) return response;

    response = await fetch(request);

    // Cache only successful responses
    if (response.ok) {
      const cached = new Response(response.body, response);
      cached.headers.set('Cache-Control', 's-maxage=300');
      await cache.put(cacheKey, cached.clone());
    }

    return response;
  },
};
```

## Tiered caching

```
User → Edge PoP (L1) → Regional Shield (L2) → Origin

L1: 300+ edge locations, small cache, high hit rate for popular content
L2: 10-20 regional caches, larger cache, absorbs L1 misses
Origin: only handles L2 misses
```

Tiered caching reduces origin load dramatically — a cache miss at one
edge PoP is served from the regional shield instead of hitting the
origin.

## Anti-patterns

- **Short TTLs everywhere** — setting `max-age=10` on all responses
  defeats CDN caching. Short TTLs belong on rapidly changing content;
  use longer TTLs with stale-while-revalidate for most content.
- **Purge-everything on deploy** — purging the entire CDN cache on every
  deployment causes a thundering herd on the origin. Use versioned URLs
  for static assets and targeted purges for dynamic content.
- **No Vary header** — serving different content based on headers
  (Accept-Encoding, Accept-Language) without a `Vary` header causes
  the CDN to serve the wrong variant.
- **Caching authenticated responses publicly** — forgetting `private`
  or `no-store` on user-specific responses means User A sees User B's
  data from the CDN cache.

## Gotchas

- **Vary header explosion** — `Vary: *` or `Vary: Cookie` effectively
  disables caching because every request has unique cookies. Only vary
  on headers the CDN can normalize.
- **Origin shield vs. direct origin** — without a shield tier, every
  edge PoP fetches from the origin independently on cache miss. For 300
  PoPs, a popular uncached resource triggers 300 origin requests
  simultaneously.
- **Cache key normalization** — query parameters, trailing slashes, and
  URL encoding create distinct cache entries for the same content.
  Normalize cache keys in edge compute or CDN rules.
- **POST/PUT cache invalidation** — CDNs only cache GET/HEAD by default.
  After a POST that mutates data, the corresponding GET cache entry is
  not automatically invalidated. Use tag-based purging on write.

## Verification

- Static assets use content-hashed filenames with immutable caching.
- HTML and API responses use appropriate Cache-Control with
  stale-while-revalidate.
- Tag-based purging is configured for dynamic content types.
- No authenticated or user-specific responses are cached publicly.
- CDN cache hit ratio is monitored (target: > 90% for static, > 60% for
  dynamic).
- Tiered caching (origin shield) is enabled to reduce origin load.

## Related

- `documentation/docs/policies/performance/core-web-vitals.md`
- `documentation/docs/policies/cloudflare/workers-development-patterns.md`
- `documentation/docs/policies/frontend/image-optimization.md`

## Source URLs (verified 2026-08-16)

- Web caching strategies 2026 — https://www.digitalapplied.com/blog/web-caching-strategies-2026-engineering-reference
- CDN cache invalidation strategies — https://enterno.io/en/articles/cdn-cache-invalidation
- CDN caching strategies guide — https://oneuptime.com/blog/post/2026-01-30-cdn-caching-strategies/view
- CDN caching innovations — https://blog.blazingcdn.com/en-us/innovations-in-data-caching-in-cdn-networks
