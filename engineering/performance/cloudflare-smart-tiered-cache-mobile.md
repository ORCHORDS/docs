# Cloudflare Smart Tiered Cache: Topology, Cache Reserve, and Mobile Origin Hit Reduction

**Date:** 2026-08-22
**Author:** example.com
**Status:** active

## Symptom

example project CDN cache analytics show a per-PoP hit ratio of 55–65 % for cover-art
images and audio waveform JSON despite correct Cache-Control headers. Mobile
users in regions with lower Cloudflare PoP density (Southeast Asia, Latin
America) experience `CF-Cache-Status: MISS` on assets that were recently served
to a different PoP. Each MISS causes the PoP to fetch from the example project R2
origin, adding 80–250 ms of origin-fetch latency to the mobile response chain.
The root cause is that Cloudflare's default caching is flat: each of the 300+
PoPs maintains an independent cache with no sharing between them.

## Context

Cloudflare's network topology (as of 2026) has three cache layers that can be
activated for example project:

1. **Edge PoPs** (~300+ locations) — serve the majority of requests; default
   flat-cache, no inter-PoP sharing.
2. **Smart Tiered Cache** — designates a small set of "upper-tier" PoPs as
   cache parents for groups of lower-tier edge PoPs; a MISS at a lower PoP
   checks the upper tier before going to origin.
3. **Cache Reserve** — persists CDN objects to R2 so even upper-tier cache
   evictions resolve from R2 rather than from the application origin.

Mobile users are disproportionately affected by flat-cache misses because
mobile traffic is geographically dispersed and request rates per PoP are lower,
reducing per-PoP hit ratios for long-tail assets.

## Smart Tiered Cache topology

```
Flat cache (default):
  Edge PoP A (São Paulo)   ──MISS──→  example project Origin (R2)
  Edge PoP B (Buenos Aires)──MISS──→  example project Origin (R2)
  Edge PoP C (Santiago)   ──MISS──→  example project Origin (R2)

  Each PoP independently fetches from origin on a miss.
  Origin hit rate: one per PoP per cold object.

Smart Tiered Cache (enabled):
  Edge PoP A (São Paulo)   ──MISS──→  Upper Tier (Miami)──MISS──→ Origin (R2)
  Edge PoP B (Buenos Aires)──MISS──→  Upper Tier (Miami)──HIT───→ (served from tier)
  Edge PoP C (Santiago)   ──MISS──→  Upper Tier (Miami)──HIT───→ (served from tier)

  After PoP A warms the upper tier, PoPs B and C get cache hits
  from Miami rather than going to R2 origin.
  Origin hit rate: one per upper-tier PoP per cold object (much lower).
```

## Enabling Smart Tiered Cache (Cloudflare dashboard / API)

```bash
# Enable Argo Smart Routing + Tiered Cache via Cloudflare API.
# Smart Tiered Cache is part of Argo (paid feature, billed per GB transferred).

ZONE_ID="<your-zone-id>"
CF_TOKEN="<your-api-token>"

# Enable Argo Smart Routing (required for Smart Tiered Cache)
curl -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/argo/smart_routing" \
  -H "Authorization: Bearer ${CF_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"value": "on"}'

# Enable Tiered Cache (Smart topology) via Cache Rules or Zone Setting
curl -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/cache/tiered_cache_smart_topology_enable" \
  -H "Authorization: Bearer ${CF_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"value": "on"}'
```

```
Smart Tiered Cache — expected origin hit-rate reduction for example project:

  Asset type           Flat-cache origin hits   Tiered-cache origin hits
  ────────────────────────────────────────────────────────────────────────
  Cover art (popular)  1 per PoP / TTL window   1 per upper tier / TTL window
  Cover art (long tail) 1–2 per PoP per day      1 per upper tier per day
  Waveform JSON        1 per PoP / TTL window   1 per upper tier / TTL window
  Audio tracks         1 per PoP / TTL window   1 per upper tier / TTL window

  Upper-tier count (~10–15 globally) vs flat PoPs (~300):
  expected origin traffic reduction: 90–95 % for popular assets.
```

## CF-Cache-Status header meanings

```
Header value        Meaning
────────────────────────────────────────────────────────────────────────────
HIT                 Served from the edge PoP's cache.
MISS                Not in edge PoP cache; fetched from origin (or upper tier).
EXPIRED             Was in cache but past TTL; fetched fresh and re-stored.
STALE               Served stale copy; background revalidation in progress
                    (stale-while-revalidate in effect).
REVALIDATED         Confirmed with origin via conditional request (304); served
                    from cache without re-transferring body.
UPDATING            Origin revalidation ongoing; prior response served to client.
BYPASS              Cache bypassed due to Cache-Control: no-store, cookie,
                    query string, or Page Rule bypass.
DYNAMIC             Response marked uncacheable by Cloudflare (dynamic content
                    or no appropriate Cache-Control directive).
NONE/UNKNOWN        Cloudflare could not determine cache status (rare; origin
                    returned unusual headers).

Tiered Cache adds a second dimension visible in Logpush:
  cf.tiered_cache_status: HIT  → upper tier served the request
  cf.tiered_cache_status: MISS → upper tier also missed; went to origin
```

## Cache Reserve for R2 objects

```typescript
// Cache Reserve stores CDN objects durably in R2 so they survive
// PoP-level eviction. For example project's immutable audio and cover art,
// Cache Reserve means the "origin" for the CDN is effectively R2
// in Cloudflare's own network — not the Workers application.

// Enable Cache Reserve via Cloudflare API:
// PATCH /zones/{zone_id}/cache/cache_reserve
// { "value": "on" }

// With Cache Reserve enabled, the cache lookup chain becomes:
//   1. Edge PoP cache   → HIT: serve immediately
//   2. Upper tier       → HIT: fill edge PoP, serve
//   3. Cache Reserve    → HIT: fill upper tier + edge, serve
//   4. R2 / Worker      → MISS: fill all layers, serve

// Cache Reserve is billed per-GB stored and per-operation; it is most
// cost-effective for large, infrequently accessed objects (audio tracks)
// rather than small, frequently accessed ones (API JSON).
```

```
Layer latency from mobile client perspective (example project, 4G, 100 ms RTT to PoP):

  Cache layer           Approx. added latency   CF-Cache-Status
  ──────────────────────────────────────────────────────────────
  Edge PoP HIT          0 ms (in-PoP memory)    HIT
  Upper tier HIT        ~15–30 ms (PoP-to-tier) MISS (edge), HIT (tier)
  Cache Reserve HIT     ~30–60 ms (tier-to-R2)  MISS (edge+tier)
  R2 / Worker origin    ~80–250 ms              MISS (all layers)
```

## Mobile origin hit rate: measuring the improvement

```typescript
// Emit CF-Cache-Status per request to Workers Analytics Engine for
// per-device-type hit ratio tracking.

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const res = await fetch(req);   // let Cloudflare serve from cache or origin

    const cacheStatus = res.headers.get("CF-Cache-Status") ?? "UNKNOWN";
    const deviceType  = req.headers.get("CF-Device-Type")  ?? "unknown";

    // Write to Analytics Engine (WAE) for dashboarding
    env.AE.writeDataPoint({
      blobs:   [cacheStatus, deviceType, new URL(req.url).pathname],
      indexes: [cacheStatus],
    });

    return res;
  },
};

// Query in Analytics Engine SQL:
// SELECT blob2 AS device_type,
//        blob1 AS cache_status,
//        COUNT() AS requests
// FROM   example project_cache_metrics
// WHERE  timestamp > NOW() - INTERVAL '1' HOUR
// GROUP  BY device_type, cache_status
// ORDER  BY requests DESC
```

```
Typical mobile origin hit reduction after enabling Smart Tiered Cache
and Cache Reserve (example project media subdomain, 7-day window):

  Metric                       Before    After    Change
  ────────────────────────────────────────────────────────
  Mobile CF-Cache-Status: MISS   41 %      6 %    −85 %
  Mobile P95 TTFB (cover art)   310 ms    42 ms   −86 %
  Origin (R2) GET requests     100 K/hr  12 K/hr  −88 %
  Argo bandwidth cost            —       +$0.10/GB  (new)
```

## Anti-patterns

- **Enabling Smart Tiered Cache without Argo Smart Routing** — Tiered Cache
  requires Argo to be active; without it the API call succeeds but routing
  does not change.
- **Setting `Cache-Control: no-store` on cacheable media** — overrides both
  Smart Tiered Cache and Cache Reserve; every request hits origin regardless
  of topology. A common mistake when a Worker adds security headers globally.
- **Relying solely on CF-Cache-Status: MISS to diagnose origin load** — MISS
  at the edge PoP does not distinguish upper-tier hits from true origin hits;
  use Logpush `cf.tiered_cache_status` for accurate origin-hit counting.
- **Cache Reserve on high-churn API JSON** — Cache Reserve adds per-operation
  cost; applying it to endpoints with sub-minute TTLs results in high R2
  operation costs with negligible hit-rate benefit.
- **Mixing authenticated and public assets on the same CDN path** — if a
  Worker conditionally returns `Cache-Control: private` for authed requests,
  Cloudflare will BYPASS cache for those requests; keep public and private
  assets on separate paths to maximise tiered-cache hit rates for public content.

## Gotchas

- **Smart Tiered Cache is eventually consistent across topology changes** —
  when Cloudflare updates its PoP-to-upper-tier assignments (rare but
  possible), cached objects may briefly appear as MISSes in new PoPs.
- **Cache Reserve objects are eventually purged if not accessed** — Cache
  Reserve is not permanent storage; objects not accessed within Cloudflare's
  retention window (currently 30 days) may be evicted and fetched from origin
  on next request.
- **Purge propagation with Tiered Cache** — a `cache.purge` call must
  propagate to both edge PoPs and upper tiers; use tag-based purging rather
  than URL purging to ensure all tiers are cleared for mutable assets.
- **CF-Cache-Status reflects the edge PoP's view only** — an upper-tier HIT
  still shows `MISS` at the edge PoP level in the response header; you need
  Logpush or Analytics Engine to see the full tier breakdown.
- **Argo billed on transferred bytes, not requests** — for large audio files
  the upper-tier-to-edge transfer adds Argo costs; model this against origin
  bandwidth savings before enabling on audio tracks.

## Verification

- Enable Logpush for Cache fields including `CacheTieredFill`; confirm
  `cf.tiered_cache_status: HIT` appears for inter-tier fills after warm-up.
- Monitor Cloudflare Analytics → Caching dashboard: "Saved Bandwidth" metric
  increases after Smart Tiered Cache enables.
- Run WebPageTest from five geographically dispersed mobile locations (e.g.,
  São Paulo, Singapore, Lagos) for the same cover-art URL; assert all return
  `CF-Cache-Status: HIT` after initial warm-up requests.
- Workers Analytics Engine query for `cache_status = 'MISS'` grouped by
  `device_type`; assert mobile MISS rate ≤ 10 % after 1-hour warm-up window.
- Verify Cache Reserve: purge an object, request it once, then check Logpush
  for `CacheReserveUsed: true` on the second request (fill from Reserve).

## Related

- `documentation/categories/performance/cdn-cache-strategy.md`
- `documentation/categories/performance/cache-control-headers.md`
- `documentation/categories/performance/cloudflare-r2-presigned-cdn-acceleration.md`
- `documentation/categories/performance/argo-smart-routing-mobile-latency.md`
- `documentation/categories/performance/edge-caching-cdn-invalidation.md`

## Sources

- Cloudflare Smart Tiered Cache — https://developers.cloudflare.com/cache/how-to/tiered-cache/
- Cloudflare Cache Reserve — https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/
- CF-Cache-Status values — https://developers.cloudflare.com/cache/concepts/cache-responses/
- Argo Smart Routing — https://developers.cloudflare.com/argo-smart-routing/
- Cloudflare Logpush Cache fields — https://developers.cloudflare.com/logs/reference/log-fields/zone/http_requests/
