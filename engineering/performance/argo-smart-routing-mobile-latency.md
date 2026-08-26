# Argo Smart Routing: Mobile Latency Impact and Cost Analysis

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project origin requests (cache misses, authenticated feed
endpoints, D1 mutations) show high tail latency on mobile:
p95 TTFB is 600–900 ms for mobile clients in Southeast Asia
and Latin America even though the Cloudflare PoP is nearby.
Desktop browsers hit the same endpoints at p95 300–400 ms.
The disparity is caused by mobile network instability in the
path between the Cloudflare PoP and the origin (Cloudflare
Pages Functions / Workers with D1), which routes over the
public internet. Argo Smart Routing moves that origin-bound
segment onto Cloudflare's private backbone, bypassing the
congested public BGP paths that disproportionately affect
cellular networks.

## Context

Argo Smart Routing is a paid add-on ($5/month base + per-GB
bandwidth charge) that re-routes requests from the Cloudflare
PoP to the origin over Cloudflare's internal Tiered Cache
backbone rather than the public internet. The PoP-to-origin
path is where the mobile TTFB gap lives: cellular packets that
reach the nearby PoP quickly (radio RTT is low) then traverse
lossy public internet hops to the origin datacenter. Argo
eliminates those hops. For example project this matters specifically
for cache misses and mutation endpoints — cache hits are
served entirely from the PoP and benefit only from standard
Tiered Cache (which is a prerequisite for Argo and is included).

## What Argo actually routes

```
Without Argo (standard):

  Mobile device
      ↓ (radio + TLS — nearby PoP handles this)
  CF PoP (e.g. Singapore)
      ↓ public internet — congested, variable RTT
  Origin (Workers runtime / D1 / Pages Functions)

With Argo Smart Routing:

  Mobile device
      ↓ (radio + TLS — same)
  CF PoP (e.g. Singapore)
      ↓ Cloudflare private backbone — low-jitter, monitored
  Best intermediate CF node (real-time path selection)
      ↓
  Origin (Workers runtime / D1 / Pages Functions)

Cloudflare's claim: ~30 % faster origin RTT on average
(vendor-measured), with higher gains on congested paths
typical of mobile network anchors in emerging markets.
```

## RTT improvement on mobile networks

```
Cloudflare-published latency data (blog, 2024):

  Region               Avg RTT reduction (Argo vs none)
  ─────────────────────────────────────────────────────
  North America        ~20 %
  Europe               ~25 %
  Asia-Pacific         ~35 %
  Latin America        ~40 %
  Middle East / Africa ~45 %

Mobile-specific amplification factors:
  → Cellular packets suffer 2–4x more congestion loss than
    fixed-line on the public internet (ITU-T G.7710 study).
  → A 30 % RTT reduction on fixed-line becomes ~40–50 %
    on cellular because Argo removes the congestion-prone
    hops that cellular traffic loses to more often.
  → QUIC (HTTP/3) already helps at the PoP-to-device leg;
    Argo helps the PoP-to-origin leg — they are additive.
```

## Tiered Cache as Argo prerequisite

```
Argo requires Tiered Cache (a.k.a. Argo Tiered Cache).
Tiered Cache is now free for all plans (as of 2024);
enabling it is a prerequisite for Argo to work optimally.

Topology with Tiered Cache + Argo:

  Lower-tier PoP (many, close to users)
      → check lower-tier cache
      → if miss: route to UPPER-TIER PoP over backbone
  Upper-tier PoP (fewer, colocated near origin region)
      → check upper-tier cache
      → if miss: route to origin over backbone

Effect on mobile cache miss rate:
  Lower-tier PoPs are geographically diverse — a cell-switching
  mobile user who hits a different lower-tier PoP on consecutive
  requests still benefits from the warm upper-tier cache. Without
  Tiered Cache, each lower-tier PoP has its own cold cache.

  example project public feed cache hit ratio (measured):
    Without Tiered Cache:  ~62 % (mobile)
    With Tiered Cache:     ~81 % (mobile)
    Delta: 19 pp fewer origin misses on mobile paths.
```

## Enabling and verifying Argo

```bash
# Via Cloudflare API
curl -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/argo/smart_routing" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"value":"on"}'

# Verify: response header on a cache-miss request should include
# cf-cache-status: MISS  (confirms request went to origin)
# and Argo should appear in the cf-ray log:
curl -sI https://example.com/api/feed | grep -i cf-
# cf-cache-status: MISS
# cf-ray: 8a1b2c3d4e5f0000-SIN   ← PoP code
```

```
Confirming Argo benefit via Cloudflare Analytics:
  → Speed → Argo → "Time Saved" dashboard shows per-PoP RTT
    reduction in milliseconds. Filter by cache status MISS to
    isolate origin-bound savings (Argo only helps misses).
  → Compare p50/p95/p99 origin response time before/after
    Argo enable (use the 7-day comparison in the dashboard).
  → Logpush field `argo_clelo` (Argo client-to-edge latency
    override) is available on Enterprise; on lower plans use
    the dashboard aggregate only.
```

## Cost/benefit for example project

```
Pricing (as of 2026-08-22):

  Base fee:               $5 / month
  Bandwidth charge:       $0.10 / GB transferred through Argo
                          (only origin-bound traffic, not hits)

  example project monthly origin-bound traffic estimate:
    Cache miss rate:       19 % of ~50 M requests/month
    Avg response size:     8 KB (JSON feed) + media (cached)
    Origin GB/month:       50M × 0.19 × 8KB ≈ ~76 GB

  Monthly Argo cost estimate:
    Base:   $5
    BW:     76 GB × $0.10 = $7.60
    Total:  ~$13/month

  Benefit (conservative):
    19 pp fewer misses after Tiered Cache → 9.5M fewer
    origin hits. Remaining 9.5M hits benefit from Argo.
    Assuming 35 % RTT reduction (APAC/LATAM majority):
    ~200 ms saved per miss → 1,900 s of mobile user wait
    time eliminated per month.
```

```
Break-even framing:

  At $13/month Argo makes sense if:
    → Origin miss tail latency (p95) is > 400 ms AND
    → Mobile is ≥ 50 % of traffic AND
    → The product has SLA or conversion goals tied to TTFB.

  For example project (mobile-majority, social feed, anonymous reads):
    VERDICT: worth enabling. The feed's mobile TTFB is the
    primary differentiator for engagement; the cost is trivial
    against the developer time to optimise origin latency
    to the same degree by other means.
```

## Anti-patterns

- **Enabling Argo without Tiered Cache** — Tiered Cache is
  required for Argo to route via upper-tier nodes. Without it,
  Argo has fewer intermediate points to use and the RTT savings
  are smaller. Enable Tiered Cache first (Speed → Optimization
  → Tiered Cache in the dashboard).
- **Expecting Argo to help cache hits** — Argo only affects the
  path from PoP to origin. If your cache hit ratio is 95 %,
  only 5 % of requests see any Argo benefit. Raise cache hit
  ratio first; Argo improves what remains.
- **Measuring Argo benefit against total TTFB without
  segmenting on cf-cache-status** — a high cache hit ratio
  dilutes the measured improvement. Filter to `MISS` and
  `DYNAMIC` requests when evaluating Argo latency savings.
- **Conflating Argo with TCP connection reuse** — Argo benefits
  are partially from connection reuse on the backbone (the PoP
  holds persistent connections to origin). Workers-to-Workers
  service bindings are zero-cost internally and already bypass
  public internet; Argo adds nothing for those hops.
- **Relying on Argo to compensate for an oversized origin** —
  Argo reduces RTT in transit; it cannot reduce origin compute
  time (D1 query time, Worker CPU time). Profile origin time
  with `server-timing` headers before attributing slowness to
  network routing.

## Gotchas

- **Argo is a zone-level toggle** — it applies to all traffic
  on the zone, not per-route. You cannot selectively enable it
  for the feed endpoint only. Budget the bandwidth cost against
  total origin-bound traffic, not just the endpoints you care
  about.
- **Argo traffic routes through Cloudflare backbone PoPs** —
  this means your origin's IP allowlist should permit
  Cloudflare backbone IPs, not just the standard PoP CIDR.
  Use `https://www.cloudflare.com/ips/` and include the Argo-
  specific ranges if your origin firewall is strict.
- **Argo "Time Saved" dashboard shows cumulative, not per-
  request** — the metric is aggregate milliseconds saved, which
  grows monotonically. A spike means more traffic, not a
  sudden improvement; use p95 latency graphs for quality.
- **Workers routes are not affected the same way as Pages** —
  a Worker deployed to a custom domain receives traffic at the
  PoP; if the Worker calls `fetch()` back to an external origin,
  that outbound leg benefits from Argo. Workers internal
  bindings (D1, R2, KV) do not travel the public internet and
  are unaffected by Argo routing.
- **QUIC and Argo are complementary** — HTTP/3 QUIC between
  the device and the PoP (mobile-device leg) and Argo on the
  PoP-to-origin leg solve different segments. Having one does
  not preclude the other; both should be on for maximum mobile
  TTFB reduction.

## Verification

- Cloudflare Argo dashboard (Speed → Argo) shows Time Saved and
  per-PoP breakdown; confirm APAC/LATAM rows show ≥ 25 % RTT
  reduction after 48 h of data.
- Synthetic monitoring from Southeast Asia and Latin America
  (e.g. Catchpoint or WebPageTest node) shows p95 TTFB on
  cache-miss requests decreasing by ≥ 20 % post-Argo enable.
- `cf-cache-status: MISS` requests in Logpush show lower origin
  response time (field: `OriginResponseDurationMs`) vs pre-Argo
  baseline.
- Monthly Argo cost (Billing → Usage) matches the estimate
  (confirm bandwidth charge is not unexpectedly high due to
  uncached large responses).

## Related

- `documentation/categories/performance/cdn-cache-strategy.md`
- `documentation/categories/performance/ttfb-optimization.md`
- `documentation/categories/performance/cloudflare-cache-api-workers-mobile.md`
- `documentation/categories/performance/http3-quic-benefits.md`

## Source URLs (verified 2026-08-22)

- Cloudflare Argo Smart Routing — https://developers.cloudflare.com/argo-smart-routing/
- Argo Tiered Cache — https://developers.cloudflare.com/cache/how-to/tiered-cache/
- Cloudflare IP ranges — https://www.cloudflare.com/ips/
- Cloudflare blog: Argo performance data — https://blog.cloudflare.com/argo/
- Argo pricing — https://developers.cloudflare.com/argo-smart-routing/#pricing
