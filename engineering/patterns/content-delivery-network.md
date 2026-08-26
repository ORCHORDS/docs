# content-delivery-network

**Issue:** CDN for static assets — when to use, how to configure
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your static assets (images, CSS, JS) are served from a single
origin. Users in Asia have 500ms latency. The page feels slow.
You turn on a CDN. Latency drops to 50ms. The CDN costs $0.

## Root cause
**Static assets are highly cacheable.** A CDN puts them at
the edge, close to the user. Latency drops; origin load drops.

**Source:** CF CDN (built into Pages):
https://developers.cloudflare.com/cache/

> "Cloudflare's CDN caches your content at the edge ... to
> reduce latency and origin load."

## CF Pages + CDN (built-in)

CF Pages is a CDN by default. Every static asset you deploy
is automatically cached at 300+ edge locations.

**No config needed** for the basic case.

## Cache-Control headers

The browser and CDN both respect `Cache-Control` headers:
```ts
// In functions/_middleware.ts or _headers file
const response = new Response(body, {
  headers: {
    'Cache-Control': 'public, max-age=31536000, immutable',  // 1 year
  },
});

// For dynamic responses (don't cache)
const response = new Response(json, {
  headers: {
    'Cache-Control': 'no-store',  // never cache
  },
});
```

| Cache-Control | Browser | CDN | Use |
|---|---|---|---|
| `public, max-age=N, immutable` | Cache for N sec | Cache for N sec | Versioned assets (`/static/v123/...`) |
| `public, max-age=N` | Cache for N sec | Cache for N sec | Frequently-updated static |
| `private, max-age=N` | Cache for N sec | Don't cache | Per-user responses |
| `no-store` | Don't cache | Don't cache | Sensitive / per-user |
| `no-cache` | Always revalidate | Always revalidate | Stale-while-revalidate |
| `s-maxage=N` | Ignored | Cache for N sec | CDN-only caching |

## The "immutable" pattern for versioned assets

For assets that change when the version changes:
```ts
// In your build output
/build/static/js/main.abc123.js

// The URL includes a hash; when the hash changes, the URL changes
// The browser can cache "forever" (1 year) safely
const response = new Response(jsContent, {
  headers: { 'Cache-Control': 'public, max-age=31536000, immutable' },
});
```

Most modern build tools (Vite, Webpack, Next.js) do this
automatically with content hashes in filenames.

## The stale-while-revalidate pattern

Serve stale content while fetching fresh in the background:
```ts
const response = new Response(cachedContent, {
  headers: {
    'Cache-Control': 'public, max-age=3600, stale-while-revalidate=86400',
  },
});
```

The browser uses the cached version for 1 hour. After 1 hour,
the browser serves the cached version while fetching the
fresh version in the background. The user never sees a slow
load.

## Cache invalidation

When you update a file, the CDN needs to know.

### Purge by URL
```bash
curl -X POST "https://api.cloudflare.com/client/v4/zones/<zone>/purge_cache" \
  -H "Authorization: Bearer <token>" \
  -d '{"files": ["https://example.com/static/main.js"]}'
```

### Purge by tag
```bash
curl -X POST "https://api.cloudflare.com/client/v4/zones/<zone>/purge_cache" \
  -H "Authorization: Bearer <token>" \
  -d '{"tags": ["static-assets"]}'
```

Tag-based purging is more efficient if you have many assets
to invalidate.

### Purge everything
```bash
curl -X POST "https://api.cloudflare.com/client/v4/zones/<zone>/purge_cache" \
  -H "Authorization: Bearer <token>" \
  -d '{"purge_everything": true}'
```

Use sparingly (impacts all users).

## CF-specific features

### Tiered cache
CF has a tiered cache: regional caches hold the assets,
edge caches serve the assets. The regional cache is the
"origin" for the edge caches.

For a global audience, this is great. For a regional
audience, you may want to disable tiered cache.

### Cache rules (CF dashboard)
- By URL pattern
- By header
- By cookie
- By country

Configure in CF Dashboard → Caching → Cache Rules.

### Edge cache TTL
CF has a default edge cache TTL (typically 2 hours for
HTML, 1 month for static). Override with `Cache-Control`
header.

## The "hot path" optimization

For your most-trafficked pages:
1. **Pre-render** the HTML at build time (static)
2. **Cache** the HTML at the edge (default for CF Pages)
3. **Use a service worker** to cache the page offline (PWA)

This makes the homepage load in < 100ms for the user.

## Verification
- **Test:** `test/cache-headers.test.ts > static assets have
  long Cache-Control, dynamic responses have no-store` —
  passes
- **Live:** CF Analytics shows the cache hit rate > 80%
- **Audit:** Quarterly review of cache TTLs

## Gotchas
- **`max-age=0` does NOT mean "don't cache."** It means
  "always revalidate." The browser still asks the server
  "is this still valid?" Use `no-store` to truly not cache.
- **`private` vs `public`** matters. A CDN may not cache
  `private` responses, even if `max-age` is set. For per-
  user responses, use `private, max-age=N`.
- **The Vary header** controls which request headers affect
  the cache key. `Vary: Accept-Encoding` means gzip and
  non-gzip are cached separately.
- **The `Age` header** shows how long the response has been
  in the cache. If `Age > max-age`, the response is stale.
- **Some assets shouldn't be cached** (CSRF tokens, payment
  forms, etc.). Mark them `no-store`.
- **The CDN can serve stale content during deploys.** Use
  `purge` on deploy to force fresh content.

## Related
- `cache-strategies.md` (the broader caching story)
- `next-static-export-pages.md` (static export + CDN)
- `feature-environment-promotion.md` (per-env caching)
- CF cache: https://developers.cloudflare.com/cache/
- MDN Cache-Control: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
