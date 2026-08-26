# Cache API in Workers: D1/R2 Caching and Mobile Key Strategy

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project feed requests hitting a Worker that fans out to D1 for
post metadata and R2 for media manifests are slow on mobile even
after adding Cloudflare's edge cache to static assets. The Worker
round-trips to D1 every time a request arrives because Workers
bypass the CDN layer by default — they run at the origin edge
and any caching inside them requires the Cache API explicitly.
Mobile users on social referral links (cold-cache sessions) see
300–600 ms TTFB on feed endpoints while the desktop web app
(persistent session, warm cache) reports 40–80 ms.

## Context

A Cloudflare Worker sits in front of D1 and R2 for example project:
every feed load triggers N D1 reads and M R2 HEAD calls. The
Cache API (caches.default) is the right layer to absorb repeated
reads — it is per-PoP object storage reachable synchronously
from the Worker handler, with no egress cost for cache hits.
The mobile vs desktop gap arises because mobile users generate
more cold-cache traffic (app kill/restart cycles, network
switching, background tab eviction) and because R2 latency
dominates in higher-RTT mobile cells. Correct cache key
partitioning by device type prevents serving desktop-width image
manifests to mobile clients and vice versa.

## Cache API fundamentals in a Worker

```typescript
// caches.default is the only persistent cache available to a
// Worker without Durable Objects. Keyed by Request URL.
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const cache = caches.default;

    // ── build a device-aware cache key ──────────────────────
    const cacheKey = buildCacheKey(req);

    // ── 1. cache read ────────────────────────────────────────
    const cached = await cache.match(cacheKey);
    if (cached) return cached;               // ~0 ms hit path

    // ── 2. origin fetch (D1 / R2) ───────────────────────────
    const response = await fetchFromOrigin(req, env);

    // ── 3. store (must clone; body is consumed once) ─────────
    if (response.ok) {
      const toStore = response.clone();
      // cache.put is fire-and-forget; await is optional
      ctx.waitUntil(cache.put(cacheKey, toStore));
    }

    return response;
  },
};
```

The Cache API accepts any Request object as key — URL does not
have to resolve. Use a synthetic Request to encode device type
without polluting the real request URL.

## Device-type cache key strategy (mobile vs desktop)

```typescript
// Cloudflare sets CF-Device-Type on every request that reaches
// a Worker when "Browser Integrity Check" or device detection
// is enabled in the zone. Values: mobile | desktop | tablet.
// Fall back to UA sniffing only if the header is absent.

function getDeviceType(req: Request): "mobile" | "desktop" {
  const cfType = req.headers.get("CF-Device-Type");
  if (cfType === "mobile" || cfType === "tablet") return "mobile";
  if (cfType === "desktop") return "desktop";

  // fallback: coarse UA sniff (treat unknown as desktop)
  const ua = req.headers.get("User-Agent") ?? "";
  return /mobile|android|iphone|ipad/i.test(ua)
    ? "mobile"
    : "desktop";
}

function buildCacheKey(req: Request): Request {
  const url   = new URL(req.url);
  const dtype = getDeviceType(req);

  // Append device type as a query param — the Cache API will
  // treat it as a distinct key. Do NOT leak this param to D1.
  url.searchParams.set("__dt", dtype);

  return new Request(url.toString(), {
    method:  "GET",
    headers: { "Cache-Control": req.headers.get("Cache-Control") ?? "" },
  });
}
```

```
Cache key dimensions for example project feed:

  Base URL          /api/feed?cursor=<tok>
  + device type     __dt=mobile | __dt=desktop
  + auth scope      public (anonymous) or uid-keyed (private)

  → Never mix authed and anonymous entries. If the endpoint
    returns user-specific data, skip the Cache API entirely
    or key on user ID (defeats caching for most feeds).
    example project's public feed (no auth) caches cleanly; profile
    feeds must be skipped or short-TTL / user-keyed.
```

## TTL and stale-while-revalidate patterns

```typescript
// Cache-Control on the stored response controls TTL.
// Cloudflare's Cache API respects s-maxage and
// stale-while-revalidate directives.

function buildFeedResponse(data: FeedData): Response {
  return new Response(JSON.stringify(data), {
    headers: {
      "Content-Type": "application/json",
      // public feed: serve stale for 5 s, revalidate 55 s
      "Cache-Control": "public, s-maxage=5, stale-while-revalidate=55",
      // Vary on nothing — the cache key already carries device type
    },
  });
}

// stale-while-revalidate lets the Worker return the cached copy
// immediately to the in-flight request and then revalidate in
// the background via waitUntil. Mobile clients on flaky cells
// get sub-10 ms JSON while the revalidation runs out of band.
async function revalidateInBackground(
  key: Request,
  env: Env,
  ctx: ExecutionContext
) {
  ctx.waitUntil(
    fetchFromOrigin(/* ... */).then(res => {
      if (res.ok) caches.default.put(key, res);
    })
  );
}
```

```
TTL recommendations for example project:

  Endpoint              s-maxage   stale-while-revalidate
  ──────────────────────────────────────────────────────
  /api/feed (public)    5 s        55 s
  /api/post/:id         30 s       300 s
  R2 media manifest     60 s       3600 s
  D1 user profile       0 s        –  (skip cache; auth)
  Static assets         31536000 s –  (standard CF edge cache)
```

## R2 response caching in a Worker

```typescript
// R2 object fetches (env.R2.get()) bypass Cloudflare's HTTP
// cache — you must store them via the Cache API manually.

async function fetchMediaManifest(
  key: string,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const cache    = caches.default;
  const cacheReq = new Request(`https://r2-cache.internal/${key}`);

  const hit = await cache.match(cacheReq);
  if (hit) return hit;

  const obj = await env.R2_MEDIA.get(key);
  if (!obj) return new Response("Not Found", { status: 404 });

  const headers = new Headers({
    "Content-Type": obj.httpMetadata?.contentType ?? "application/json",
    "Cache-Control": "public, s-maxage=60, stale-while-revalidate=3600",
    "ETag": obj.etag,
  });

  const res = new Response(obj.body, { headers });
  ctx.waitUntil(cache.put(cacheReq, res.clone()));
  return res;
}
```

## Viewport-aware cache splitting (advanced)

```
For image manifests, split on breakpoint instead of device type:

  Viewport bucket   Condition (Sec-CH-Viewport-Width)
  ─────────────────────────────────────────────────────
  xs                < 480 px   → mobile AVIF, 640w max
  sm                480–767px  → mobile WebP, 960w max
  md                768–1279px → desktop WebP, 1440w max
  lg                ≥ 1280px   → desktop, 2560w max

  Client Hints must be enabled on the zone and the Worker
  must advertise Accept-CH: Sec-CH-Viewport-Width.
  Not all mobile in-app browsers send Client Hints (iOS
  WebKit never does as of 2026) — fall back to CF-Device-Type
  buckets when the hint is absent.
```

## Anti-patterns

- **Caching authenticated responses** — if the Worker returns
  user-specific JSON and you write it to caches.default keyed
  only by URL, every user gets the first-cached user's data.
  Always skip the cache for auth-gated endpoints or include the
  user ID in the key (which makes caching mostly pointless).
- **Forgetting to clone before cache.put** — `response.body` is
  a ReadableStream consumed once. Calling `cache.put(key, res)`
  after having streamed `res` to the client stores an empty body.
  Always `res.clone()` and pass the clone.
- **Keying only on URL when device type matters** — a desktop-
  optimised JSON manifest (large image URLs) cached at a URL then
  served to a mobile client can balloon the mobile LCP by sending
  2×-4× the bytes needed.
- **Storing CF-Device-Type in the visible URL** — the __dt param
  used in the synthetic Request must be stripped before passing
  to D1/R2; exposing it in API responses leaks internal details.
- **Long TTLs on fast-changing feeds** — a 60 s s-maxage on a
  social feed means new posts are invisible for up to a minute.
  Use 5 s / SWR=55 s so the perceived delay is under one refresh.

## Gotchas

- **Cache API is per-PoP, not global** — warming the cache in
  one Cloudflare datacenter does not warm others. Mobile users
  roaming between cells may hit different PoPs and encounter
  cold-cache TTFB repeatedly on the same session. Design TTLs
  assuming any PoP can be cold at any time.
- **caches.default.put() is fire-and-forget** — if the Worker
  is evicted (CPU limit, memory limit, or the isolate is
  recycled) before `waitUntil` completes, the write may be lost.
  This is expected; the next request triggers another origin
  fetch and another put attempt.
- **D1 bindings are not available inside waitUntil on some
  runtime builds** — validate your runtime version; D1 reads
  inside `ctx.waitUntil` work on Workers runtime ≥ 2024-04-12.
- **CF-Device-Type is only set when Cloudflare's device detection
  is on** — toggling it off in the zone dashboard (Speed →
  Optimization) silently breaks your mobile/desktop split. Assert
  the header is present in your Worker's health-check.
- **Cache API stores full response headers** — if your origin
  returns a Set-Cookie header and you store the response, every
  subsequent cache hit will replay that cookie to all users.
  Strip Set-Cookie before `cache.put`.

## Verification

- Worker logs (Logpush) show `X-Cache: HIT` proportion per
  endpoint and per device-type key; mobile HIT ratio tracked
  separately from desktop.
- D1 query counter (Workers Analytics Engine) decreases by the
  expected factor (target: ≥ 80 % hit ratio on public feed).
- Synthetic probes from mobile-emulation (throttled 4G) show
  TTFB ≤ 80 ms on cache hits, confirming in-PoP serve latency.
- stale-while-revalidate verified by a two-request sequence:
  first response returns stale Age header; second (after 2 s)
  returns a fresher Last-Modified.
- Cache key split verified by asserting different ETags are
  stored for `/api/feed?__dt=mobile` vs `…?__dt=desktop`.

## Related

- `documentation/categories/performance/kv-read-performance.md`
- `documentation/categories/performance/d1-query-optimization.md`
- `documentation/categories/performance/cloudflare-workers-performance.md`
- `documentation/categories/performance/cdn-cache-strategy.md`
- `documentation/categories/performance/workers-kv-read-performance-mobile-cold-start.md`

## Source URLs (verified 2026-08-22)

- Cloudflare Cache API (Workers) — https://developers.cloudflare.com/workers/runtime-apis/cache/
- CF-Device-Type header — https://developers.cloudflare.com/ruleset-engine/rules-language/fields/dynamic-fields/#cfdevice_type
- stale-while-revalidate (RFC 5861) — https://datatracker.ietf.org/doc/html/rfc5861
- Cloudflare R2 Workers binding — https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- Client Hints: Sec-CH-Viewport-Width — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Sec-CH-Viewport-Width
