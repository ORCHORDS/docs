# Cloudflare Tiered Cache Parent Selection Performance

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cache hit rates remain lower than expected even after enabling Cloudflare's Tiered
Cache. Some edge PoPs consistently miss and go to origin while others hit. Enabling
"Smart Tiered Cache Topology" improves things but not uniformly — certain geographic
regions still show high origin egress. The root issue is that the default Tiered Cache
topology (Generic Tiered Cache) groups PoPs into a fixed two-tier hierarchy that may
not match your traffic distribution, while Smart Tiered Cache selects a single "upper
tier" per zone based on traffic analysis that may take 24–48 hours to converge.

## Context

Cloudflare's CDN is organized into hundreds of edge PoPs (data centers). Without
Tiered Cache, every edge PoP that experiences a cache miss goes directly to origin,
multiplying origin load by the number of active PoPs. With Tiered Cache, edge PoPs
("lower tier") first check an "upper tier" PoP before going to origin; the upper tier
acts as a regional shield, consolidating misses from many edge PoPs into fewer origin
requests.

Cloudflare offers three Tiered Cache configurations:

| Topology | Description | Plan |
|---|---|---|
| Generic Tiered Cache | Fixed regional groupings; widely available | Free+ |
| Smart Tiered Cache | Automatically selects one upper tier per zone based on historic latency | Pro+ |
| Custom Tiered Cache | Explicitly configure which PoPs serve as upper tiers | Enterprise |

The choice of upper tier(s) directly affects:
- **Cache consolidation ratio**: How many edge misses are absorbed by the tier vs.
  reaching origin.
- **Upper-tier-to-origin latency**: If the upper tier is far from the origin server,
  misses at the upper tier are more expensive than if the edge PoP had gone to origin
  directly.
- **Inter-tier bandwidth costs**: Cloudflare does not charge for inter-PoP bandwidth,
  but upper-tier cache misses that hit origin do count toward origin egress.

## Smart Tiered Cache: How Parent Selection Works

Smart Tiered Cache analyzes the RTT (round-trip time) from each candidate upper-tier
PoP to the zone's origin server, combined with traffic volume data collected over a
rolling window. It selects the single PoP with the best trade-off between:
- Proximity to origin (low upper-tier-to-origin RTT)
- Proximity to the zone's most active edge PoPs (reduces edge-to-upper-tier RTT)
- Historical cache hit rate at that PoP for this zone's content

The selection is re-evaluated periodically. During the convergence period (up to 48
hours for a new zone or after a configuration change), Smart Tiered Cache may select
a suboptimal parent. You can observe the currently selected parent via the Cloudflare
dashboard under Caching → Tiered Cache, or via the Analytics API.

## Enabling and Verifying Smart Tiered Cache via Workers

```typescript
// worker/cache-debug.ts
// Inspect cache status headers to verify tiered cache behavior.
export async function fetchWithCacheDebug(
  url: string,
  env: Env
): Promise<{ status: string; tier: string | null; age: string | null }> {
  const response = await fetch(url, {
    cf: {
      // Ask Cloudflare to cache this request through the tiered cache.
      cacheTtl: 3600,
      cacheEverything: true,
    },
  });

  // CF-Cache-Status values:
  // HIT    — served from edge or upper-tier cache
  // MISS   — not in cache; fetched from origin through upper tier
  // BYPASS — cache bypassed
  // DYNAMIC — not cacheable
  // REVALIDATED — stale content revalidated
  const cacheStatus = response.headers.get("cf-cache-status") ?? "unknown";
  const age = response.headers.get("age");

  // CF-Ray encodes the serving PoP as the last 3 chars: e.g., "abc123-LHR"
  const cfRay = response.headers.get("cf-ray") ?? "";
  const servingPoP = cfRay.split("-").pop() ?? null;

  return { status: cacheStatus, tier: servingPoP, age };
}
```

```typescript
// Sample log output for diagnosing tier behavior:
// { status: "HIT",  tier: "LHR", age: "3421" }  — served from upper tier cache
// { status: "MISS", tier: "LHR", age: null }     — upper tier miss; went to origin
// { status: "HIT",  tier: "DFW", age: "120" }    — served from edge cache
```

## Cache-Control Tuning for Tiered Cache Efficiency

A short `max-age` or aggressive `no-store` response from origin undermines every
cache tier. The upper tier respects cache directives set by the origin (unless
overridden by a Cloudflare Cache Rule).

```typescript
// worker/cache-rules.ts
// Override short origin TTLs at the edge using Edge Cache TTL.
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await fetch(request, {
      cf: {
        // Cloudflare caches this for 1 hour regardless of origin Cache-Control.
        cacheTtl: 3600,
        // Respect origin Cache-Control if it specifies longer TTL.
        cacheTtlByStatus: {
          "200-299": 3600,
          "301":     86400,
          "302":     300,
          "404":     60,
          "500-599": 0,   // Do not cache errors.
        },
      },
    });
    return response;
  },
};
```

## Measuring Upper-Tier Cache Hit Rate

Use Cloudflare Analytics Engine or the GraphQL Analytics API to measure how often
the upper tier serves requests vs. passing them to origin:

```typescript
// Cloudflare GraphQL Analytics API query (run from a trusted backend, not a Worker)
const ANALYTICS_QUERY = `
{
  viewer {
    zones(filter: { zoneTag: $zoneTag }) {
      httpRequests1hGroups(
        limit: 24
        filter: { datetime_geq: $start, datetime_leq: $end }
        orderBy: [datetime_ASC]
      ) {
        dimensions { datetime }
        sum {
          requests
          cachedRequests
          tieredCacheHits: requests  # See note below
        }
      }
    }
  }
}
`;

// Note: Tiered Cache hit/miss breakdown is available in the Enterprise Analytics
// GraphQL schema under the `httpRequestsAdaptiveGroups` dataset with
// dimension `upperTierCacheStatus`.
```

For non-Enterprise plans, use the `cf-cache-status` header logged by a Tail Worker:

```typescript
// worker/tail.ts — log cache tier behavior for every request.
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const ev of events) {
      const status = ev.response?.headers?.["cf-cache-status"] ?? "unknown";
      const ray    = ev.response?.headers?.["cf-ray"] ?? "";
      const pop    = ray.split("-").pop() ?? "unknown";

      // Write to Analytics Engine for aggregation.
      // env.ANALYTICS.writeDataPoint({ ... });
      console.log(`${pop} ${status}`);
    }
  },
};
```

## Custom Tiered Cache Topology (Enterprise)

Enterprise zones can specify explicit upper-tier PoPs using the Cloudflare API:

```bash
# Set a custom tiered cache topology via the Cloudflare API.
curl -X PUT "https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/cache/tiered_cache_smart_topology_enable" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"value": "on"}'

# For Enterprise Custom Tiered Cache, configure via the dashboard or
# Cloudflare Terraform provider: cloudflare_tiered_cache resource.
```

For most zones, Smart Tiered Cache is the right choice. Custom topology is warranted
when:
- The origin is in a region where no nearby Cloudflare PoP is selected as the parent.
- Traffic is highly concentrated in a specific region (e.g., all users in Southeast
  Asia) but the auto-selected parent is geographically distant.
- A specific upper tier PoP is known to have a direct fiber path to the origin
  (e.g., a co-located PoP).

## Anti-patterns

- **Enabling Tiered Cache without long enough `Cache-Control` TTLs**: Tiered Cache
  only helps if content is actually cached. An origin that returns `Cache-Control:
  max-age=0` or `no-store` on every response makes the tier a pure pass-through with
  added latency.
- **Using `Cache-Control: no-cache` for content that does not change per-user**:
  `no-cache` forces revalidation on every request, bypassing the tiered cache even
  when the content is identical for all users. Use `stale-while-revalidate` instead.
- **Vary: * or Vary: Cookie on public assets**: Excessive `Vary` headers cause cache
  fragmentation at the upper tier; every unique cookie value results in a separate
  cache entry. Strip unnecessary `Vary` fields at the edge for public assets.
- **Expecting immediate convergence after enabling Smart Tiered Cache**: Allow 24–48
  hours for the parent selection algorithm to stabilize before drawing conclusions
  from hit rate metrics.
- **Confusing `CF-Cache-Status: MISS` with Tiered Cache being disabled**: A MISS
  simply means the content was not in cache at any tier — it does not indicate Tiered
  Cache is inactive. Tiered Cache is working if a subsequent request for the same URL
  returns `HIT`.

## Gotchas

- **Tiered Cache and `Cache-Control: private`**: Responses with `Cache-Control:
  private` are not stored at any Cloudflare tier and are never served from cache,
  regardless of Tiered Cache configuration. This is correct behavior; private
  responses are user-specific.
- **Workers `fetch` with `cf.cacheKey`**: Custom cache keys set in a Worker's `fetch`
  call affect both edge and upper-tier cache keying. Ensure the key is stable across
  PoPs (do not include PoP-specific values in the cache key).
- **Tiered Cache and Argo Smart Routing conflict**: If Argo Smart Routing is also
  enabled, origin-bound requests from the upper tier travel via Argo's optimized path.
  This is additive, not conflicting, but the latency contribution of each should be
  measured separately.
- **Cache Reserve interaction**: Cache Reserve (persistent cache tier backed by R2)
  operates below the Tiered Cache upper tier in the lookup chain:
  Edge PoP → Upper Tier PoP → Cache Reserve → Origin.
  A hit in Cache Reserve still avoids origin but costs an R2 read per miss.

## Verification

1. Enable Smart Tiered Cache in the Cloudflare dashboard (Caching → Tiered Cache →
   Smart Tiered Cache Topology: On).
2. Warm the cache by fetching a set of URLs from multiple geographic locations (use
   `curl` from a VPS in different regions or a synthetic monitoring tool).
3. After 10 minutes, re-fetch the same URLs. Inspect `CF-Cache-Status: HIT` and the
   `Age` header (increasing `Age` values confirm the upper-tier cache is serving
   content).
4. Compare origin request counts in the Cloudflare dashboard (Analytics → Traffic)
   before and after enabling Tiered Cache. A well-configured zone typically sees a
   40–80 % reduction in origin requests for cacheable content.

```bash
# Quick verification from two geographically distinct locations.
# First fetch (cold):
curl -sI https://example.com/static/app.js | grep -i "cf-cache-status"
# cf-cache-status: MISS

# Second fetch (warm — from same or nearby PoP):
curl -sI https://example.com/static/app.js | grep -i "cf-cache-status"
# cf-cache-status: HIT
```

## Related

- `cloudflare-smart-tiered-cache-mobile.md`
- `cache-reserve-persistent-tier-origin-offload.md`
- `cdn-cache-strategy.md`
- `edge-caching-patterns.md`
- `cache-stampede-prevention.md`
- `targeted-cdn-cache-control-precedence.md`

## Sources

- Cloudflare Tiered Cache documentation: https://developers.cloudflare.com/cache/how-to/tiered-cache/
- Smart Tiered Cache topology: https://developers.cloudflare.com/cache/how-to/tiered-cache/#smart-tiered-cache-topology
- Cloudflare Cache Reserve: https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/
- Cloudflare Analytics GraphQL API: https://developers.cloudflare.com/analytics/graphql-api/
