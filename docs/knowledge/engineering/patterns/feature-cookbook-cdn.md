# feature-cookbook-cdn

**Issue:** CDN — setup, cache, purge
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your static assets are slow. A user in Asia has 500ms
latency for your CSS file. The page takes 3s to load.
You add a CDN. The latency drops to 50ms. The page loads
in 1s. The user is happy.

## Root cause
**Static assets should be at the edge.** Without a CDN,
the user gets them from the origin (slow).

**Source:** CF CDN docs:
https://developers.cloudflare.com/cache/

## The "CF Pages + CDN" pattern

CF Pages is a CDN by default. Every static asset is
served from 300+ edge locations.

```
my-app.pages.dev/  →  CF CDN
                  ↓
                Origin (if not cached)
```

No setup needed.

## The "Cache-Control" pattern

For cache control, set the headers:
```ts
// In a Worker or page header
const response = new Response(body, {
  headers: {
    'Cache-Control': 'public, max-age=31536000, immutable',  // 1 year
  },
});

// For dynamic responses
const response = new Response(json, {
  headers: {
    'Cache-Control': 'no-store',
  },
});
```

The browser + CDN respect the headers.

## The "versioned assets" pattern

For versioned assets, use a hash in the filename:
```ts
// Build output
/build/static/js/main.abc123.js
/build/static/css/main.def456.css

// HTML references
<script ></script>
<link rel="stylesheet"  />
```

When the hash changes, the URL changes; the browser
fetches the new version.

## The "stale-while-revalidate" pattern

For "always fresh, but fast":
```ts
const response = new Response(body, {
  headers: {
    'Cache-Control': 'public, max-age=300, stale-while-revalidate=86400',
  },
});
```

The browser uses the cached version for 5 min; after that,
it serves the cached version while fetching the fresh
version in the background.

## The "cache invalidation" pattern

For cache invalidation on deploy:
```bash
# Purge everything
curl -X POST "https://api.cloudflare.com/client/v4/zones/<zone>/purge_cache" \
  -H "Authorization: Bearer <token>" \
  -d '{"purge_everything": true}'

# Or purge by URL
curl -X POST "https://api.cloudflare.com/client/v4/zones/<zone>/purge_cache" \
  -H "Authorization: Bearer <token>" \
  -d '{"files": ["https://example.com/static/main.js"]}'

# Or purge by tag (CF Enterprise)
curl -X POST "https://api.cloudflare.com/client/v4/zones/<zone>/purge_cache" \
  -H "Authorization: Bearer <token>" \
  -d '{"tags": ["static-assets"]}'
```

The cache is invalidated after a deploy.

## The "CDN + image" pattern

For images, use CF Images for transformation:
```ts
const image = `https://imagedelivery.net/${env.CF_IMAGES_HASH}/w=200,h=200,fit=cover/image-id`;

// Transformations
const thumbnail = `https://imagedelivery.net/${env.CF_IMAGES_HASH}/w=100,h=100,fit=cover/image-id`;
const large = `https://imagedelivery.net/${env.CF_IMAGES_HASH}/w=1920,h=1080,fit=cover/image-id`;
```

CF Images serves WebP/AVIF automatically.

## The "CDN + R2" pattern

For files in R2, use the public URL:
```ts
// Public R2 bucket
const url = `https://pub-xyz.r2.dev/${key}`;

// Custom domain
const url = `https://cdn.example.com/${key}`;
```

R2 serves from CF's edge; no egress fees.

## The "CDN + Worker" pattern

For dynamic content with caching:
```ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cache = caches.default;

    // 1. Check cache
    const cached = await cache.match(request);
    if (cached) {
      // 2. Optionally refresh in background
      ctx.waitUntil(refreshCache(request, env));
      return cached;
    }

    // 3. Generate the response
    const response = await generateResponse(request, env);

    // 4. Cache for 5 minutes
    const cacheable = new Response(response.body, response);
    cacheable.headers.set('Cache-Control', 'public, max-age=300');
    ctx.waitUntil(cache.put(request, cacheable.clone()));

    return response;
  },
};
```

The Worker is the origin; the CDN is the cache.

## The "cache key" pattern

The cache key is the request URL + relevant headers:
```ts
// Default: just the URL
const cache = await caches.default.match(request);

// Custom: with a header
const cacheKey = new Request(request.url, {
  method: 'GET',
  headers: { 'Accept-Language': 'en' },
});
const cached = await cache.match(cacheKey);
```

The `Vary` header tells the CDN to cache by header:
```ts
response.headers.set('Vary', 'Accept-Language');
```

## The "CDN cost" pattern

CF CDN is included with Pages. No extra cost for the
caching itself.

For R2 + custom domain, you pay R2 egress (which is $0
on CF).

## The "cache hit rate" pattern

Track cache hit rate:
```ts
let hits = 0;
let misses = 0;

async function getCached(request: Request, env: Env): Promise<Response> {
  const cached = await caches.default.match(request);
  if (cached) {
    hits++;
    return cached;
  }
  misses++;
  return null;
}

// Periodically report
setInterval(() => {
  const total = hits + misses;
  console.log({ cacheHitRate: total > 0 ? hits / total : 0 });
}, 60_000);
```

A high hit rate (> 80%) means the cache is working.

## The "CDN" anti-patterns

### 1. No Cache-Control
- **Issue:** The CDN caches forever (or never)
- **Fix:** Set explicit headers

### 2. Wrong Cache-Control
- **Issue:** Cache-Control: no-store on assets
- **Fix:** Cache-Control: public, max-age=...

### 3. Long cache with no versioning
- **Issue:** Users see old assets after deploy
- **Fix:** Versioned filenames

### 4. PII in cached responses
- **Issue:** User A's data is cached for user B
- **Fix:** Don't cache authenticated responses

### 5. No purge after deploy
- **Issue:** Stale assets after deploy
- **Fix:** Purge the cache

## The "image optimization" pattern

For images, use modern formats:
```html
<picture>
  <source srcset="/image.avif" type="image/avif" />
  <source srcset="/image.webp" type="image/webp" />
  <img  alt="Description" />
</picture>
```

The browser picks the best format.

## The "preload" pattern

For critical resources:
```html
<link rel="preload"  as="style" />
<link rel="preload"  as="script" />
<link rel="preload"  as="font" crossorigin />
```

The browser fetches critical resources early.

## The "cache headers" anti-patterns

### 1. Cache-Control: no-store on static assets
```ts
// ❌ Bad: static asset with no-store
response.headers.set('Cache-Control', 'no-store');
```

### 2. Cache-Control: public on private data
```ts
// ❌ Bad: user data with public
response.headers.set('Cache-Control', 'public');
```

### 3. Cache-Control: max-age=0 (always revalidate)
```ts
// ❌ Bad: revalidates every time
response.headers.set('Cache-Control', 'max-age=0');
// Use no-cache if you want revalidation
```

## Verification
- **Test:** Static assets are cached
- **Test:** Dynamic responses are not cached
- **Test:** Cache is purged on deploy
- **Live:** Cache hit rate > 80%
- **Audit:** Quarterly review of cache

## Gotchas
- **The "cache forever" anti-pattern.** Without
  versioning, users see old content forever.
- **The "cache user data" anti-pattern.** A cached
  response with user data is a leak.
- **The "no CDN" anti-pattern.** Static assets without a
  CDN are slow.
- **The "cache without Vary" anti-pattern.** A cache
  without Vary can return the wrong content for the
  user.
- **The "no purge" anti-pattern.** A deploy without
  cache purge = users see old content.

## Related
- `content-delivery-network.md`
- `cloudflare/workers-cache-api.md`
- `caching-strategies-detail.md`
- `feature-cookbook-perf.md`
- `cache-strategies.md`
- CF CDN: https://developers.cloudflare.com/cache/
- CF Cache: https://developers.cloudflare.com/cache/concepts/default-cache-behavior/
