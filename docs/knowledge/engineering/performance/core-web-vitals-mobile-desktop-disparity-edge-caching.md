# Mobile-vs-Desktop Core Web Vitals Disparity Behind a CDN

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Your Cloudflare-cached site shows all-green Core Web Vitals in
PageSpeed Insights when you check it from the office — but Search
Console reports failing URLs, and the field data toggle reveals the
split: desktop passes everything, mobile fails INP and LCP. Adding
more edge caching (higher cache hit ratio, tiered cache, longer
TTLs) improved TTFB globally yet moved mobile INP by exactly
nothing. For example project (example.com) this is the default state, not an
anomaly: traffic arrives overwhelmingly from mobile in-app browsers
via social referrals, so the origin-level CWV verdict is effectively
the mobile verdict — the desktop numbers are a rounding error.

## Context

CrUX segments all field data by device (`form_factor`: PHONE,
DESKTOP, TABLET) and Google evaluates pass/fail per segment. The
2025 Web Almanac (July 2025 CrUX) measured 56% of desktop origins
passing all three vitals vs 48% on mobile — an 8-point structural
gap. The gap is concentrated in INP: 97% of desktop origins record
good INP vs only 77% on mobile (a 20-point gap), because INP is
dominated by main-thread CPU work and median mobile hardware is
several times slower than a desktop. Edge caching attacks network
latency (TTFB, LCP's network fraction) which is why a CDN narrows
the LCP gap but cannot touch the INP gap — cached JavaScript
arrives faster and then executes just as slowly. Budgets for a
mobile-majority product must be set against mobile field data.

## The device gap in 2025-2026 field data

```
Metric (good, % of origins)   Desktop   Mobile   Gap
──────────────────────────────────────────────────────────
All three CWV (Almanac 2025)    56%      48%     8 pts
All three CWV (DebugBear '25)   57.1%    49.7%   ~7 pts
LCP  ≤ 2.5s                     74%      62%    12 pts
INP  ≤ 200ms                    97%      77%    20 pts
CLS  ≤ 0.1                      72%      81%    -9 pts (!)

TBT p50 (lab, HTTP Archive)     92 ms    1,916 ms
TBT p75 (lab, HTTP Archive)     336 ms   4,193 ms

One vendor study puts median p75 INP at ~120 ms desktop vs
~248 ms mobile — directional, not CrUX-confirmed, but it
matches the pass-rate picture: typical mobile p75 INP sits
past the 200 ms threshold; desktop rarely gets close.

CLS is the one vital where mobile WINS (simpler single-column
layouts, fewer ads/sidebars shifting content).
```

## What edge caching fixes — and what it cannot

```
Layer                       Edge cache effect     Metric moved
──────────────────────────────────────────────────────────────
DNS/TLS/connection RTT      Terminated at edge    TTFB
HTML delivery               Cache hit ≈ ~10-50ms  TTFB, FCP
Static assets (JS/CSS/img)  Served from PoP       LCP (network
                                                  fraction)
Main-thread JS execution    NONE — same bytes,    INP, TBT
                            same slow CPU
Hydration cost              NONE                  INP
Third-party script work     NONE (often not even  INP
                            proxied via your CDN)
Layout shift behavior       NONE                  CLS

Rule of thumb: a CDN compresses the parts of the waterfall
that happen BEFORE the browser starts working. INP happens
AFTER. A 4x slower phone CPU runs your cached 300KB bundle
4x slower no matter which PoP served it.
```

For example project: Next.js static export on Cloudflare Pages means HTML
and assets are already fully edge-cached — TTFB is essentially
solved. Every remaining mobile CWV point lives in client-side
JavaScript and rendering, which no Cloudflare cache setting
influences.

## Reading field data per device (CrUX / PSI)

```bash
# CrUX API — query the PHONE segment explicitly.
# Omitting formFactor aggregates all devices and lets desktop
# traffic mask mobile failures.
curl -s "https://chromeuserexperience.googleapis.com/v1/records:queryRecord?key=$CRUX_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "origin": "https://example.com",
    "formFactor": "PHONE",
    "metrics": ["largest_contentful_paint",
                "interaction_to_next_paint",
                "cumulative_layout_shift"]
  }'
```

```
Reading the results:

  → CrUX is a 28-day rolling window, updated daily ~04:00 UTC.
    A fix ships today; the p75 fully reflects it only after
    ~28 days. Use your own RUM (web-vitals library) for
    immediate feedback, CrUX for the ranking-relevant verdict.

  → PageSpeed Insights shows field data with a Mobile/Desktop
    toggle at the top. The Lighthouse lab score below it is a
    SEPARATE simulation (emulated Moto G Power class device,
    throttled 4G for mobile) — lab-mobile can differ wildly
    from field-mobile.

  → Low-traffic URLs fall back to origin-level data in PSI;
    check the "Origin" label so you know which you're reading.

  → CrUX History API gives weekly time series per form factor —
    use it to prove (or disprove) that a deploy moved mobile p75.
```

## Mobile-specific levers that actually close the gap

```
Lever                          Moves       Why it works on mobile
──────────────────────────────────────────────────────────────
Ship less JS (code-split,      INP, LCP    Less parse/compile/
tree-shake, drop polyfills)                execute on slow CPU
Reduce hydration cost          INP         Hydration is a long
(RSC, islands, defer                       main-thread task on
non-interactive components)                4x-slower silicon
Third-party script diet        INP, TBT    Analytics/embeds run
(facade, delay, Partytown)                 on the same thread
Break long tasks               INP         scheduler.yield() /
                                           chunked handlers keep
                                           input latency bounded
Font strategy                  CLS, LCP    font-display:optional
                                           + size-adjust fallback
Smaller images via srcset /    LCP         Less decode work AND
CDN transforms                             fewer bytes on radio
```

For example project specifically: the feed and composer are the
interaction-heavy surfaces; budget them with the lab TBT proxy on
a throttled mobile profile, and treat every new client dependency
as a mobile-INP decision.

## Cloudflare levers: what helps mobile, what doesn't

```
Feature                     Helps mobile CWV?   Metric
──────────────────────────────────────────────────────────────
Early Hints (103)           Yes (Chromium/FF;   LCP, FCP
                            Safari ignores it)
HTTP/3 + QUIC               Yes — lossy radio   TTFB, LCP
                            links benefit most
Image transformations /     Yes — right-sized   LCP
Polish / AVIF               bytes for viewport
Speed Brain (speculation    Yes on Chromium     TTFB→~0, LCP
rules, Chromium 121+)       121+; ~45% LCP cut  on NEXT nav
                            on successful
                            prefetches
Tiered Cache / Cache        Marginal once hit   TTFB
Reserve                     ratio is high
Argo Smart Routing          Origin-bound only   TTFB (misses)
Rocket Loader / Mirage      NO — known to break
                            modern JS apps
Anything cache-related      NO effect on INP    —
```

```
Speed Brain caveats (relevant to example project):
  → Chromium-only (121+). Android in-app browsers are mostly
    Chromium; ALL iOS in-app browsers are WebKit → no effect.
  → Prefetches cached content only; never hits Workers/origin.
  → Not compatible with *.pages.dev preview domains — measure
    on the production custom domain only.
  → Improves the NEXT navigation, never the landing page —
    social-referral entry pages (our majority case) see no
    benefit on first load.
```

## Anti-patterns

- **Judging "the site is fast" from desktop office hardware** — an
  M-series laptop on fiber is a ~97%-INP-pass environment. Your
  median user is on a mid-range Android over cellular inside an
  in-app webview. Always demo and debug on a throttled profile.
- **Buying more caching to fix INP** — cache hit ratio and INP are
  uncorrelated. If desktop passes and mobile fails, the problem is
  main-thread work, and the fix is shipping/executing less JS.
- **Reading aggregated CrUX without form_factor** — blended data
  hides a failing PHONE segment behind a passing DESKTOP one.
  Google evaluates per device; so should your dashboards.
- **Setting budgets from desktop numbers** — for a mobile-majority
  product, the desktop budget is decorative. Set LCP/INP/TBT
  budgets against mobile field p75 and mobile lab emulation.
- **Enabling Rocket Loader to "fix mobile JS"** — it rewrites
  script loading and routinely breaks Next.js hydration. JS cost
  is reduced in the bundler, not at the proxy.

## Gotchas

- **CLS is often BETTER on mobile** (81% vs 72% good in 2025) —
  don't assume mobile loses every metric; single-column layouts
  shift less. A mobile CLS regression is therefore more alarming.
- **The 28-day window cuts both ways** — a bad deploy poisons the
  ranking signal for up to a month after the revert. Gate deploys
  with lab TBT so regressions never reach the field window.
- **Lab "mobile" is one fixed device** — Lighthouse emulates a
  single mid-tier phone. Field mobile is a distribution; your p75
  user is likely slower than the emulated device in some regions.
- **In-app browsers under-report** — CrUX only collects from
  Chrome (and only on eligible platforms); much of example project's
  webview traffic is invisible to CrUX. First-party RUM via the
  web-vitals library is the only way to see those sessions.
- **Speed Brain's 45% LCP win is conditional** — it applies to
  successful prefetches of subsequent navigations on Chromium,
  not to overall origin LCP, and not to iOS at all.

## Verification

- CrUX API queried with `formFactor: "PHONE"` and results tracked
  separately from desktop in the performance dashboard.
- CWV budgets (LCP, INP-via-TBT, JS size) set against mobile
  field p75, not desktop.
- web-vitals RUM deployed and segmented by device + in-app
  browser UA, covering traffic CrUX cannot see.
- Lighthouse CI runs the mobile (throttled) profile as the
  gating configuration.
- Early Hints, HTTP/3, and image transformations enabled;
  Rocket Loader and Mirage confirmed off.
- Speed Brain measured on the production custom domain against
  Chromium next-navigation LCP, with iOS excluded from the
  comparison.

## Related

- `documentation/docs/policies/performance/web-performance-budgets-core-web-vitals.md`
- `documentation/docs/policies/performance/core-web-vitals-overview.md`
- `documentation/docs/policies/cloudflare/cache-device-type-segmentation-mobile-desktop.md`
- `documentation/docs/policies/cloudflare/client-hints-adaptive-image-delivery-mobile.md`

## Source URLs (verified 2026-08-17)

- Web Almanac 2025: Performance — https://almanac.httparchive.org/en/2025/performance
- CrUX API (form factors, 28-day window) — https://developer.chrome.com/docs/crux/api
- Cloudflare Speed Brain docs — https://developers.cloudflare.com/speed/optimization/content/speed-brain/
- DebugBear: 2025 in Web Performance — https://www.debugbear.com/blog/2025-in-web-performance
- CWV Benchmarks 2026 (pass-rate reference) — https://www.digitalapplied.com/blog/core-web-vitals-benchmarks-2026-pass-rate-reference
