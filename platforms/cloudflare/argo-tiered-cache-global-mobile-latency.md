# Argo Smart Routing and Tiered Cache: Global Mobile Latency

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A user taps a TikTok link from Jakarta or Lagos. The page
feels slow. The CF-Cache-Status header on that request reads
MISS. The origin server in us-east-1 handled it — adding
~200ms of transoceanic round-trip on top of the cellular last
mile. Meanwhile a desktop user in New York City gets a HIT
from a PoP 10km away and sees the same page in under 500ms.
The disparity is not in the code. It is in the cache topology
and the routing path for the misses that do reach origin.

example project is a Next.js static export on Cloudflare Pages with
a Worker API. Social-referral traffic distributes load across
hundreds of edge PoPs worldwide. Mobile users arriving at
long-tail PoPs on first visit pay the steepest latency tax.

## Context

Cloudflare operates ~330 edge PoPs globally. A "long-tail"
PoP in a lower-traffic city (Mombasa, Medan, Asunción) sees
few requests per URL relative to Frankfurt or Chicago. Low
volume means content expires or is evicted before the next
visitor arrives, so those PoPs have a structurally lower
cache-hit ratio. Mobile users disproportionately hit these
PoPs: cellular networks aggregate at the nearest metro PoP
rather than routing through a high-traffic hub. For social-
referral traffic — bursts of first-time visitors — warm cache
at that PoP cannot be assumed.

Two complementary Cloudflare features address both sides of
the miss penalty:

  1. Tiered Cache — raises hit ratio by adding an upper-tier
     that fills misses without reaching origin.
  2. Argo Smart Routing — reduces the cost of misses that do
     reach origin by routing the PoP→origin segment across
     Cloudflare's private backbone instead of the public
     internet, avoiding congested peering points.

They stack: fewer misses AND cheaper misses.

## Argo Smart Routing: backbone vs public internet

```
Without Argo:
  CF edge PoP → public internet → origin
  Path traverses BGP-selected hops across multiple ASes.
  Congestion at a peering point adds variable, unpredictable
  latency — worse during peak hours in Asia-Pacific and EMEA.

With Argo Smart Routing:
  CF edge PoP → Cloudflare private backbone → origin
  Cloudflare samples ~102M req/s across its network to detect
  real-time congestion; selects the lowest-latency path per
  request. The gain is measured as TTFB on the PoP→origin leg.

Measured impact:
  Average improvement    ~30% faster than direct routing
  OKCupid (documented)   36% drop in TTFB after enabling Argo
  Biggest beneficiaries  geographically distant origins, PoPs
                         with poor public peering (Jakarta to
                         us-east-1 is a prime example)

Critical framing: Argo only helps cache MISSES. A cached
response never leaves the Cloudflare network, where the
private backbone is already used implicitly. Argo+Tiered Cache
compounds: Tiered Cache eliminates many misses; Argo makes
the remaining misses faster.
```

## Tiered Cache topology

```
Without Tiered Cache:
  Every edge PoP that misses → requests from origin directly.
  100 PoPs missing the same asset → up to 100 origin requests.

With Tiered Cache:
  Edge PoP misses → upper-tier PoP → (if miss) → origin.
  Only 1–3 upper-tier DCs contact origin per asset. Edge PoPs
  fill from the warm upper-tier, collapsing duplicate misses.

Topology options (2025–2026):

Topology          Plans          Description
──────────────────────────────────────────────────────────────
Smart             All plans      CF picks the single best
                                 upper-tier per origin using
                                 live latency probes. Zero
                                 config beyond the toggle.
Generic Global    Enterprise     ~40 DCs act as upper-tiers.
                                 More redundancy, but not
                                 recommended with Regional.
Regional          Enterprise     Adds a regional mid-tier
                                 between the edge PoP and the
                                 upper-tier. Cuts tail miss
                                 RTT by 50–100ms for distant
                                 PoPs. Best for global traffic
                                 with origins in 1–2 regions.
Custom            Enterprise     Account team designs topology
                                 for specific origin layout.
Cache Reserve     Paid add-on    R2-backed persistent store as
                  (all plans)    the final tier before origin.

Regional Tiered Cache call chain:
  Edge PoP (Jakarta) → MISS
    → Regional tier (APAC hub, e.g. Singapore)
      → HIT: served; subsequent Jakarta misses → HIT here
      → MISS: upper-tier → origin → fills regional + edge
```

## Cache Reserve: persistent R2 tier

```
Cache Reserve sits behind Tiered Cache, in front of origin:

  Edge PoP → upper-tier → Cache Reserve (R2) → origin

Assets are written to R2 automatically on cache fill and
persist for a default 30-day retention period, reset on each
read. Long-tail content that ages out of edge/upper-tier LRU
before the next request — exactly the profile of social-
referral bursts — is served from R2 instead of origin.

Eligibility requirements:
  min freshness TTL     10 hours (s-maxage or max-age)
  Content-Length        must be present in origin response
  File type             original assets only (no image
                        transformation variants)

Pricing (2026):
  Storage               $0.015 / GB-month
  Class A ops (writes)  $4.50 / million
  Class B ops (reads)   $0.36 / million

A Cache Reserve miss (origin fill) generates Class A + Class B.
A Cache Reserve hit generates one Class B op.

Tiered Cache MUST be enabled alongside Cache Reserve. Without
it every edge PoP miss triggers a separate R2 read, multiplying
Class B costs and negating the hit-ratio benefit. Cloudflare
warns in the dashboard if Cache Reserve is active without a
tiered topology.
```

## Why mobile pays the highest miss penalty

```
Signal                Desktop (NYC)   Mobile (Jakarta)
──────────────────────────────────────────────────────────────
Typical PoP type      Major hub       Long-tail or regional
Cache-hit ratio       ~85%            ~40–55% (low-volume PoP)
Miss RTT to origin    ~25ms           ~170–220ms transoceanic
Cellular last-mile    +5–10ms         +40–120ms (variable)
LCP on cache HIT      ~0.6s           ~1.0–1.4s
LCP on cache MISS     ~1.4s           ~3.8–5.0s

Why the gap compounds:
  • Social-referral is first-visit heavy — no warm cache for
    the URL at that PoP, regardless of platform-wide traffic.
  • Cellular PoPs aggregate at nearest metro; secondary cities
    hit smaller, lower-traffic PoPs with weaker hit ratios.
  • Cellular last-mile RTT is higher and more variable than
    wired broadband. Each extra network segment compounds.
  • A miss on a 200ms RTT origin is 8× worse than a miss on
    a 25ms RTT origin. Argo cuts the first leg; Tiered Cache
    eliminates the miss. Regional Tiered Cache cuts the RTT
    from Jakarta to Singapore instead of Jakarta to origin.
```

## Configuration for Next.js on Cloudflare Pages

```
# _headers file (repo root, committed alongside static export)
# Cloudflare Pages serves this automatically.

/_next/static/*
  Cache-Control: public, max-age=31536000, immutable

/*
  Cache-Control: public, s-maxage=3600, stale-while-revalidate=86400
```

```bash
# Enable Smart Tiered Cache via Cloudflare API
ZONE_ID="your_zone_id"
CF_TOKEN="your_api_token"

curl -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/cache/tiered_cache_smart_topology_enable" \
  -H "Authorization: Bearer ${CF_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"value": "on"}'

# Enable Argo Smart Routing
curl -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/argo/smart_routing" \
  -H "Authorization: Bearer ${CF_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"value": "on"}'
```

```
Dashboard paths:
  Argo          Speed > Optimization > Argo Smart Routing
  Tiered Cache  Caching > Tiered Cache → select "Smart"
  Regional      Caching > Tiered Cache → Regional Tiered Cache
                (Enterprise; requires Smart or Custom selected)
  Cache Reserve Caching > Cache Reserve → Enable storage sync
  Cloud hint    Caching > Tiered Cache → Cloud region hint
                (set for AWS/GCP/Azure origins; free all plans)
```

## Measuring the impact

```
Argo Analytics (Dashboard > Analytics > Performance):
  Origin Response Time Histogram:
    Blue bars   = direct routing baseline
    Orange bars = Argo Smart Route path
    Geo map     = TTFB delta per CF data center; negative
                  values mean direct was faster (rare edge case)
  Threshold: requires ≥500 origin requests in last 48 hours.

Cache-hit ratio by colo (GraphQL Analytics API):
  query {
    viewer {
      zones(filter: {zoneTag: $zoneTag}) {
        httpRequests1hGroups(
          filter: {datetime_gt: $start}
          orderBy: [coloCode_ASC]
        ) {
          dimensions { coloCode }
          sum { cachedRequests requests }
        }
      }
    }
  }
  Target: cachedRequests / requests per colo.
  Low-ratio colos (JAK, LOS, ASU) are primary beneficiaries
  of Tiered Cache and the baseline to track post-enablement.

CacheTieredFill metric (http_requests logs):
  Cloudflare logs a CacheTieredFill event when the upper-tier
  fills the edge — confirming Tiered Cache is active on that
  request path and not being bypassed by cache rules.

TTFB distribution (before/after Argo):
  Expect ≥20% reduction in p75 and p95 TTFB on cache misses
  from distant PoPs within 48h of enabling.
```

## Anti-patterns

- **Cache Reserve without Tiered Cache** — every edge miss
  generates a Class A + Class B R2 operation per PoP. Cost
  multiplies and hit-ratio benefit collapses. Always pair.
- **Short s-maxage on HTML (< 1h)** — content expires from
  the upper-tier before long-tail PoPs can reuse the warm
  fill. Use stale-while-revalidate to extend effective
  freshness without serving stale data to users.
- **Expecting Argo to help cache hits** — Argo only routes
  the PoP→origin segment. HIT responses never reach origin;
  Argo has no effect on them.
- **Generic Global topology with Regional Tiered Cache** —
  Cloudflare explicitly recommends against this combination.
  Use Smart or Custom topology when enabling Regional.
- **Omitting cache headers on a static export** — Next.js
  static export emits no Cache-Control by default. Without
  explicit headers or a Cache Rule, CF applies a 2-hour
  default edge TTL for HTML. Define headers in `_headers`.

## Gotchas

- **Argo is metered per GB transferred** — pricing is usage-
  based (check the dashboard estimator). High-traffic zones
  should baseline transfer volume before enabling to avoid
  unexpected billing.
- **Regional Tiered Cache is Enterprise-only** — the largest
  improvement for globally distributed mobile traffic requires
  an Enterprise contract. Smart Tiered Cache (all plans) still
  delivers meaningful hit-ratio improvement on its own.
- **Cloud region hint accelerates Smart topology convergence**
  — without a hint, CF uses latency probes which may take
  time to converge. For a known origin (AWS us-east-1), set
  the hint immediately at setup.
- **Cache Reserve 10-hour TTL floor** — assets with freshness
  < 10h are ineligible. API responses and short-lived pages
  will not be stored in Cache Reserve.
- **Argo Analytics 500-request threshold** — low-traffic
  zones may not see analytics data for days after enabling.
  Use the GraphQL API to pull raw TTFB percentiles instead.

## Verification

- Smart Tiered Cache enabled: Caching > Tiered Cache shows
  "Smart" topology selected; CacheTieredFill events appear
  in http_requests logs.
- Argo Smart Routing enabled: Speed > Optimization confirms;
  Analytics histogram shows orange bars within 48h.
- `_headers` committed with long TTL on `/_next/static/*`
  and s-maxage ≥ 3600 with stale-while-revalidate on `/*`.
- Cache Reserve enabled and Tiered Cache confirmed active
  (no dashboard warning about missing Tiered Cache pairing).
- Cloud region hint configured for origin cloud region.
- GraphQL cache-hit ratio query shows lift at long-tail colos
  (JAK, LOS, others) vs pre-enablement baseline.
- CF-Cache-Status: HIT confirmed from previously-miss colos
  after warm-up via curl or Cloudflare Trace mode.

## Related

- `documentation/categories/cloudflare/smart-placement-best-practices.md`
- `documentation/categories/performance/cdn-cache-strategy.md`
- `documentation/categories/cloudflare/cache-device-type-segmentation-mobile-desktop.md`
- `documentation/categories/cloudflare/pages-best-practices.md`
- `documentation/categories/cloudflare/r2-best-practices.md`

## Source URLs (verified 2026-08-17)

- Tiered Cache — https://developers.cloudflare.com/cache/how-to/tiered-cache/
- Cache Reserve — https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/
- Argo Smart Routing overview — https://developers.cloudflare.com/argo-smart-routing/
- Argo Analytics — https://developers.cloudflare.com/argo-smart-routing/analytics/
- Introducing Regional Tiered Cache — https://blog.cloudflare.com/introducing-regional-tiered-cache
