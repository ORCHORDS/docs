# Cloudflare Cache Hit Ratio Optimization

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Analytics shows a cache hit ratio of 35–50 % for a content-heavy site. Origin
bandwidth costs are high, TTFB from cache MISSes is 400–800 ms, and traffic spikes cause
origin overload. The expectation was 80–90 % hit rate after enabling Cloudflare's CDN.

---

## Context

Cloudflare caches a response only when several conditions are simultaneously true:

1. The resource URL scheme + host + path + relevant `Vary` fields map to a unique cache key.
2. The origin response includes a cacheable `Cache-Control` directive (`max-age > 0`,
   `s-maxage`, or Cloudflare's edge TTL overrides).
3. The request does not carry a `Cookie` header for cookies that are *not* stripped by a
   Cache Rule.
4. The response status code is cacheble (200, 206, 301, 302, 404, etc.).
5. The request method is `GET` or `HEAD`.

Low hit ratios almost always trace to one of: (a) cookies preventing caching, (b) unnecessary
query-string parameters fragmenting the cache key, (c) missing or too-short TTLs, (d) high
cardinality `Vary` headers inflating the key space, or (e) no Cache Reserve for less-frequent
assets.

---

## Diagnosing Current Hit Ratio

```bash
# Pull cache status breakdown from the GraphQL Analytics API
curl -s -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ viewer { zones(filter: { zoneTag: \"$ZONE_ID\" }) {
      httpRequests1dGroups(limit: 30, filter: { date_geq: \"2026-08-16\" }) {
        sum { cachedRequests requests }
      }
    } } }"
  }' | jq '.data.viewer.zones[0].httpRequests1dGroups[].sum'
```

The `cf-cache-status` response header on individual requests gives per-request resolution:
`HIT`, `MISS`, `EXPIRED`, `REVALIDATED`, `UPDATING`, `STALE`, `BYPASS`, `DYNAMIC`.

`BYPASS` is the primary culprit for low hit ratios. It appears when a request carries a
recognized session cookie or when the origin sends `Cache-Control: private` / `no-store`.

---

## Cache Rules for Cookie Bypass Elimination

Cloudflare automatically bypasses cache when a request contains *any* `Cookie` header unless
a Cache Rule overrides that behaviour. Most sites set analytics, A/B test, or consent cookies
on every visitor, causing blanket cache bypasses.

```
# Cloudflare Cache Rule (via Terraform / Wrangler / Dashboard)
# Rule: cache static assets regardless of cookies

Expression:
  (http.request.uri.path matches "\\.(css|js|woff2?|ttf|otf|eot|svg|png|jpg|jpeg|webp|avif|gif|ico|mp4|pdf)$")

Cache Settings:
  Cache eligibility:          Eligible for cache
  Edge TTL:                   Override origin, 1 year (31536000 s)
  Browser TTL:                Override origin, 1 year
  Cache key - Query string:   Ignore all (or include specific params)
  Cache key - Cookie header:  Remove all (or remove specific cookie names)
```

For HTML pages that are genuinely personalised, add a secondary rule that skips caching only
when a *specific* session cookie is present:

```
Expression:
  (http.cookie contains "session_id=")

Cache Settings:
  Cache eligibility: Bypass cache
```

This allows anonymous page views (no `session_id`) to be cached while still bypassing cache
for authenticated users.

---

## Query String Normalisation

UTM parameters, ad-click IDs (`fbclid`, `gclid`, `ttclid`, `msclkid`), and pagination tokens
create hundreds of cache-key variants for the same underlying content.

Cache Rule → Cache key → Query string settings:

| Strategy | Setting | Use-case |
|---|---|---|
| Ignore all query params | `Ignore` | Fully static pages |
| Include allowlist only | `Include specific` → `[page, category]` | Paginated listing |
| Exclude blocklist | `Exclude specific` → `[fbclid, gclid, utm_*]` | Content pages |

Cloudflare also supports the `No-Vary-Search` response header (RFC draft) which lets the
origin declare which query params are irrelevant to content, allowing the edge to consolidate
keys server-side without a Cache Rule.

---

## TTL Tuning

Default Cloudflare TTLs honour origin `Cache-Control: max-age` values, but many origins send
short TTLs (60–300 s) as a conservative default. Edge TTL overrides let you cache longer at
the CDN without changing origin headers:

```
# Via Cloudflare Cache Rule
Edge TTL: Override origin → 86400 s  (1 day for HTML)
Edge TTL: Override origin → 31536000 s (1 year for versioned assets)
```

For versioned assets (filename contains a content hash), set a 1-year edge and browser TTL.
For HTML, a 5–60 minute edge TTL with `stale-while-revalidate` keeps hit ratio high while
allowing reasonably fresh content.

---

## Cache Reserve for Long-Tail Assets

Cache Reserve is a persistent R2-backed cache tier. Assets evicted from the in-memory/SSD
edge cache are re-served from Cache Reserve rather than from the origin, eliminating the MISS
spike on rarely-accessed assets.

Enable per-zone in the Cloudflare dashboard under **Caching → Cache Reserve**. Cache Reserve
only applies to cacheable assets; the same Cache Rules that control edge TTL govern eligibility.

Cost: Cache Reserve charges for storage ($0.015 / GB-month) and cache read operations.
Break-even occurs when origin bandwidth savings exceed storage cost — typically at >50 GB of
unique cached content with a sparse request distribution.

---

## Vary Header Cardinality Reduction

A high-cardinality `Vary` header fragments the cache into many variants, reducing effective
hit rate. Common offenders:

- `Vary: User-Agent` — thousands of UA strings, effectively disables caching
- `Vary: Accept-Encoding` — safe, Cloudflare normalises this automatically
- `Vary: Cookie` — bypasses cache for all cookie-carrying requests

Replace `Vary: User-Agent` with Cloudflare's **device-type cache keys** (separate cache
buckets for mobile/desktop/tablet at the CDN layer) and serve a unified response per device
class rather than per UA string.

```
# Cache Rule: split cache by device type (replaces Vary: User-Agent)
Cache key - Device type: Separate cache for mobile / desktop
```

Remove `Vary: Cookie` from origin responses and use Cookie-based Cache Rule exclusions
instead, which gives fine-grained control without fragmenting the key space.

---

## Workers Cache API for Programmatic Control

When Cache Rules are not granular enough, a Worker can inspect the request and explicitly
populate the cache:

```typescript
export default {
  async fetch(request: Request): Promise<Response> {
    const cache = caches.default;
    const cacheKey = new Request(normaliseUrl(request.url), request);

    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    const response = await fetch(request);

    if (response.ok && isCacheable(request, response)) {
      const responseToCache = new Response(response.clone().body, response);
      responseToCache.headers.set('Cache-Control', 'public, max-age=3600, stale-while-revalidate=86400');
      // Strip cookies before storing
      responseToCache.headers.delete('Set-Cookie');
      await cache.put(cacheKey, responseToCache);
    }

    return response;
  },
};

function normaliseUrl(url: string): string {
  const u = new URL(url);
  // Remove tracking params
  ['fbclid', 'gclid', 'utm_source', 'utm_medium', 'utm_campaign'].forEach(p => u.searchParams.delete(p));
  return u.toString();
}

function isCacheable(req: Request, res: Response): boolean {
  if (req.method !== 'GET') return false;
  const cc = res.headers.get('Cache-Control') ?? '';
  return !cc.includes('private') && !cc.includes('no-store');
}
```

---

## Anti-patterns

**Caching with session cookies present.** Storing a response that embeds user-specific data
(name, cart count, CSRF token) into the shared cache causes data leakage between users.
Always strip `Set-Cookie` before calling `cache.put()` or ensure the cache key includes the
session identifier (which defeats hit ratio improvements).

**Vary: User-Agent on origin.** Generates O(10 k) cache variants per URL. Replace with CDN-
level device-type splitting.

**Short TTLs on versioned assets.** A file named `app.a3f9c2.js` will never change; caching
it for only 5 minutes wastes the cache. Set 1-year TTLs on any URL containing a content hash.

**No Cache Reserve on large asset libraries.** Long-tail assets (rarely-requested images,
PDFs, archived pages) get evicted from edge caches quickly. Without Cache Reserve every
request for them is an origin hit.

---

## Gotchas

- `cf-cache-status: DYNAMIC` appears for responses that Cloudflare has explicitly decided not
  to cache, often because the origin sent `Set-Cookie`. It is *not* the same as `BYPASS`.

- Purging cache (via API or dashboard) resets the warm-up period. After a bulk purge, expect
  a temporary hit ratio drop until the edge re-populates.

- Cache Rules are evaluated top-to-bottom and the first matching rule wins. Order rules from
  most-specific to least-specific.

- Cache Reserve has a minimum object size of 512 KB by default. Adjust if you need smaller
  objects persisted.

---

## Verification

1. Open DevTools Network tab → filter by `cf-cache-status` response header → confirm static
   assets show `HIT` on second request.
2. In Cloudflare Analytics → Caching → check **Cache Hit Ratio** over a 7-day window after
   rule changes.
3. Use `curl -sI https://example.com/app.a3f9c2.js | grep -i cf-cache-status` from multiple
   geographic locations to confirm edge caching is active globally.

---

## Related

- `cloudflare-cache-rules-vs-workers-cache-api.md`
- `cache-api-stale-if-error-fallback.md`
- `cache-stampede-prevention.md`
- `cdn-cache-strategy.md`
- `workers-cache-api-stale-while-revalidate.md`
- `cache-reserve-persistent-tier-origin-offload.md`

---

## Sources

- Cloudflare Cache Rules documentation: https://developers.cloudflare.com/cache/how-to/cache-rules/
- Cloudflare Cache Reserve: https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/
- cf-cache-status values: https://developers.cloudflare.com/cache/concepts/default-cache-behavior/
- No-Vary-Search draft: https://wicg.github.io/no-vary-search/
