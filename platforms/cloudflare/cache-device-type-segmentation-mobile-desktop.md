# Cache Device-Type Segmentation: Mobile Getting Desktop Content

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Mobile users intermittently receive the desktop variant of a page —
or desktop users get the mobile variant — but only when the response
came from Cloudflare's edge cache (`cf-cache-status: HIT`). Bypassing
cache always serves the correct variant. The disproportion is
irregular: some colos serve the right version, others the wrong one,
depending on which device type populated that colo's cache first.
Adding `Vary: User-Agent` at the origin does not fix it.

## Context

Cloudflare's edge cache keys on scheme + host + path + query string
by default. It does **not** key on `User-Agent`, and it does not
honor `Vary: User-Agent` for cache segmentation (Cloudflare only
respects `Vary` for images, to serve correct formats per browser
capability). Any origin that renders different HTML for mobile vs
desktop under the same URL — adaptive serving instead of responsive
design — will have its variants overwrite each other in cache.

example project relevance: the web app is a Next.js static export on
Cloudflare Pages, so the HTML is identical per URL and immune to
this class of bug. The risk appears the moment any Worker route
starts branching on `CF-Device-Type` or `User-Agent` while the
route is also cached (Cache API, cache rules, or
`cf: { cacheEverything: true }` fetches).

## How device-type cache segmentation actually works

```
Wrong (silently broken):
  Origin varies HTML on User-Agent
  + Cache Everything rule
  + Vary: User-Agent response header
  → Cloudflare ignores Vary for non-image assets
  → first requester's variant is cached for everyone

Right, option A — Cache Rules "cache by device type":
  Cache Rule → Cache key → "Cache by device type: On"
  → Cloudflare classifies UA as mobile / tablet / desktop
  → adds the classification to the cache key
  → sends CF-Device-Type request header to origin
  → origin renders per CF-Device-Type
  → three cache entries per URL, one per device class

Right, option B — custom cache key (Enterprise):
  Cache key includes user-agent-derived values or headers
  → finer segmentation (specific browsers, bots)
  → cardinality warning: keying on raw UA explodes
    the cache key space and craters hit ratio

Right, option C — avoid the problem:
  Responsive design, one HTML for all devices
  (what a static export gives you for free)
```

## Worker-level segmentation

```javascript
// Worker route that varies on device type AND caches correctly:
// put the device class INTO the cache key URL, never rely on Vary.
export default {
  async fetch(request, env, ctx) {
    const deviceType = request.headers.get('CF-Device-Type') ?? 'desktop';
    const url = new URL(request.url);

    // Synthetic cache key — device class becomes part of the key
    const cacheKey = new Request(
      `${url.origin}${url.pathname}?__device=${deviceType}`,
      request,
    );

    const cache = caches.default;
    let response = await cache.match(cacheKey);
    if (!response) {
      response = await renderForDevice(deviceType, request, env);
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
    }
    return response;
  },
};
```

`CF-Device-Type` is only populated when a cache rule with
"cache by device type" is active on the zone (or the legacy
`cache_by_device_type` Page Rule setting). Without it the header
is absent and every request falls into the fallback branch.

## Diagnosing a mixed cache

```
1. Reproduce with explicit UAs against the same colo:
   curl -sI https://app.example.com/page \
     -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 ...)" \
     | grep -iE 'cf-cache-status|cf-ray'
   curl -sI https://app.example.com/page \
     -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64 ...)" \
     | grep -iE 'cf-cache-status|cf-ray'

2. Same cf-ray colo + both HIT + different body sizes on
   MISS vs HIT → variants are overwriting each other.

3. Check for Cache Everything rules covering HTML, then check
   whether any origin/Worker logic branches on UA.
```

## Anti-patterns

- **Relying on `Vary: User-Agent`** — Cloudflare does not use it
  as a cache key input for HTML/JS/CSS; it is honored for image
  format negotiation only.
- **Keying the cache on the full raw User-Agent** — thousands of
  UA strings per device class; hit ratio collapses and the origin
  absorbs the misses. Key on the three-way device class instead.
- **Fixing mobile/desktop bleed with `Cache-Control: no-store` on
  HTML** — it works, but throws away edge caching entirely when a
  device-type cache key would have kept it.
- **Sniffing UA in a cached Worker route without putting the
  result in the cache key** — the branch runs only on MISS; HITs
  serve whatever device class populated the entry.

## Gotchas

- **Tablet is a third class** — Cloudflare classifies mobile /
  tablet / desktop. Origins that only handle mobile/desktop get
  tablet requests as a separate cache partition with the fallback
  rendering, tripling debugging confusion.
- **The legacy Page Rule and the new Cache Rule coexist** — zones
  migrated from Page Rules can have `cache_by_device_type` set at
  one path level and unset at another; irregularity then depends
  on which rule matched the path.
- **Browser cache is a second layer** — after fixing the edge key,
  users who cached the wrong variant locally keep it until their
  browser revalidates. Purge + short `max-age` on HTML limits the
  tail.
- **`CF-Device-Type` classification is UA-heuristic** — new device
  UAs (foldables, in-app browsers with custom UA suffixes) can
  land in an unexpected class; do not build entitlement or layout
  correctness on top of it, only optimization.

## Verification

- No zone-level Cache Everything rule covers UA-varying HTML
  without "cache by device type" enabled on the same rule.
- Worker routes that branch on device class embed the class in
  their synthetic cache key.
- curl with mobile and desktop UAs against the same colo returns
  the correct variant on HIT for both.
- Responsive (not adaptive) rendering confirmed for the static
  export so the entire class of bug stays impossible for Pages
  assets.

## Related

- `documentation/categories/cloudflare/cache-rules-migration.md`
- `documentation/categories/cloudflare/smart-placement-best-practices.md`
- `documentation/categories/performance/cdn-cache-strategy.md`
- `documentation/categories/performance/core-web-vitals-mobile-desktop-disparity-edge-caching.md`

## Source URLs (verified 2026-08-17)

- Cache by device type (Cache Rules example) — https://developers.cloudflare.com/cache/how-to/cache-rules/examples/cache-device-type/
- Cache keys — https://developers.cloudflare.com/cache/how-to/cache-keys/
- Serve tailored content based on device type — https://developers.cloudflare.com/cache/advanced-configuration/serve-tailored-content/
- Cache by device type (APO reference) — https://developers.cloudflare.com/automatic-platform-optimization/reference/cache-device-type/
- Vary for images — https://blog.cloudflare.com/vary-for-images-serve-the-correct-images-to-the-correct-browsers/
