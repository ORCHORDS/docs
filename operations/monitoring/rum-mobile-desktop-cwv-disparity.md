# RUM — Mobile vs Desktop Core Web Vitals Disparity on
# Cloudflare Pages (example project Patterns)

Date:   2026-08-22
Author: example.com
Status: active

---

## Symptom

example project Lighthouse CI scores pass (green) on desktop but field data
from Cloudflare RUM shows mobile users experiencing LCP > 4 s and
CLS > 0.25 — both "Poor" thresholds. The disparity widens after each
feature release and is most pronounced in South-East Asia and Latin
America, where mobile penetration is highest and median connection
speed is 4G with occasional 3G fallback.

---

## Context

Core Web Vitals (CWV) are browser-measured performance signals:
Largest Contentful Paint (LCP), Cumulative Layout Shift (CLS), and
Interaction to Next Paint (INP). Cloudflare Pages exposes a RUM
beacon injected automatically (`__PAGE_VITALS__`) when the feature
is enabled in the Pages dashboard. The beacon sends CWV readings to
Cloudflare's edge and surfaces them in the Speed dashboard.

Lab measurements (Lighthouse, WebPageTest) run on fixed hardware and
network conditions. Field data (RUM) reflects real user variance:
device CPU, memory pressure, network jitter, and OS-level rendering
differences. Mobile field data almost always diverges from lab data.

---

## LCP Disparity — Root Causes on example project

LCP measures when the largest visible element completes rendering.

Common example project-specific causes of mobile LCP regression:

```
Desktop LCP: ~1.2 s
Mobile LCP:  ~4.1 s  (3.4× slower)

Breakdown of the gap:
  - Hero image not `fetchpriority="high"` on mobile       +0.9 s
  - Font blocking (no `font-display: swap`)               +0.5 s
  - Render-blocking third-party script (analytics)        +0.7 s
  - TTFB from origin (CF cache miss on mobile UA variant) +0.6 s
  - LCP element swap at 768 px breakpoint (different img) +0.3 s
```

The last cause is the most insidious: if the desktop LCP element is a
wide banner and the mobile LCP element is a smaller product card
loaded lazily, the mobile LCP fires later because the lazy-loaded
element enters the viewport after initial paint.

Fix — always ensure the mobile LCP element is eagerly loaded:

```html
<!-- WRONG: lazy on mobile because it's below a CSS breakpoint swap -->
<img  class="hero-desktop" loading="lazy">
<img   class="hero-mobile"  loading="lazy">

<!-- RIGHT: mobile hero eager, desktop hero can lazy if off-screen -->
<img
     class="hero-mobile"
     loading="eager"
     fetchpriority="high"
     decoding="async">
```

---

## CLS on Mobile Scroll — example project Patterns

CLS accumulates layout shift scores. Mobile browsers trigger shifts
that desktop browsers mask:

| Shift source                        | Mobile | Desktop | Notes                    |
|-------------------------------------|--------|---------|--------------------------|
| Dynamic ad banner injection         | high   | low     | Fixed-height slots help  |
| Web font FOUT reflow                | high   | medium  | `size-adjust` descriptor |
| Sticky nav resize on scroll         | high   | none    | Mobile Chrome resizes bar|
| Image without explicit width/height | high   | high    | Always set dimensions    |
| Late-hydrated React component       | medium | low     | SSR placeholder sizing   |
| Virtual keyboard pushing content    | high   | none    | `interactive-widget` CSS |

```css
/* Prevent virtual keyboard from causing CLS on mobile */
@media (max-width: 768px) {
  html {
    height: 100%;
  }
  body {
    min-height: 100%;
    /* Opt into the new viewport-fitting behaviour */
    overflow: clip;
  }
}
```

Measure CLS per scroll depth: a shift at 80 % scroll depth
penalises users who read far but is invisible in lab tests that
only scroll to 50 %.

---

## TTFB — Edge vs Origin Disparity

Cloudflare Pages serves from the nearest PoP. TTFB should be low for
cached assets. Mobile TTFB spikes when:

1. The cache key includes a UA segment and mobile UAs are too diverse
   to achieve high cache-hit rates.
2. The Worker handling SSR is cold-starting on under-trafficked PoPs
   where mobile users roam (e.g. regional airports, rural cells).
3. Range requests from progressive image loaders bypass the CF cache.

```
TTFB histogram (RUM data, 7-day window):

Desktop p50:  38 ms  p95: 120 ms  p99: 310 ms
Mobile  p50:  71 ms  p95: 890 ms  p99: 2 100 ms
```

The p95/p99 gap indicates tail-latency issues concentrated on
mobile, not a baseline regression.

Mitigation — normalise cache keys:

```javascript
// Cloudflare Worker Cache API — collapse mobile UA variants
addEventListener("fetch", (e) => {
  const url  = new URL(e.request.url);
  const isMob = /Mobile|Android/.test(
    e.request.headers.get("User-Agent") ?? ""
  );
  const cacheKey = new Request(url.toString(), {
    headers: { "X-Device": isMob ? "mobile" : "desktop" },
  });
  e.respondWith(handleWithCacheKey(cacheKey, e.request));
});
```

---

## Reading Cloudflare Pages Speed RUM Data

The Pages Speed dashboard aggregates field CWV by:

- Date range (up to 30 days)
- Device type (mobile / desktop / tablet)
- Country

Key queries via Analytics Engine (if self-ingesting RUM):

```sql
-- LCP p75 by device, past 7 days
SELECT
  blob1  AS device,
  quantilesMerge(0.75)(metric_quantiles) AS lcp_p75
FROM example project_rum
WHERE timestamp >= NOW() - INTERVAL '7' DAY
  AND blob2 = 'LCP'
GROUP BY device
ORDER BY lcp_p75 DESC;
```

CWV thresholds (Chrome UX Report definitions):

| Metric | Good     | Needs improvement | Poor      |
|--------|----------|-------------------|-----------|
| LCP    | ≤ 2.5 s  | 2.5 s – 4.0 s     | > 4.0 s   |
| CLS    | ≤ 0.10   | 0.10 – 0.25       | > 0.25    |
| INP    | ≤ 200 ms | 200 ms – 500 ms   | > 500 ms  |
| TTFB   | ≤ 800 ms | 800 ms – 1800 ms  | > 1800 ms |

---

## Anti-Patterns

- Treating Lighthouse scores as a substitute for field CWV. Lighthouse
  uses a throttled 4G profile on a mid-range device emulation — real
  low-end Android phones with memory pressure behave worse.
- Aggregating CWV across all devices into a single p75. The example project
  SLO must be evaluated per device class.
- Optimising the LCP hero image without checking which element is
  actually the LCP element on mobile. Use DevTools Perf panel with
  "mobile" emulation, or filter RUM by `element` field.
- Ignoring INP on mobile. Long tasks from JS hydration block the
  main thread for 300 ms+ on low-end devices, causing "Poor" INP
  even when LCP looks acceptable.

---

## Gotchas

- Cloudflare Pages RUM only fires on Pages-hosted deployments, not on
  a Worker-served SPA with a custom domain.
- CLS windows reset between page navigations. SPA route changes do
  not reset the CLS accumulator in some browser versions — test
  multi-page flows on real devices.
- `fetchpriority="high"` is ignored by Safari < 17.2 (2024).
  Fallback: use `<link rel="preload">` for the LCP image.
- The Pages Speed dashboard reports the 75th percentile. A passing
  p75 can mask a very bad p95 affecting ~25 % of users — always look
  at the full histogram in RUM data when debugging.

---

## Verification

```bash
# Pull field CWV from Chrome UX Report API for the example project domain
curl -X POST \
  "https://chromeuxreport.googleapis.com/v1/records:queryRecord?key=${CUX_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example project.example.com",
    "formFactor": "PHONE",
    "metrics": ["largest_contentful_paint","cumulative_layout_shift","interaction_to_next_paint"]
  }' | jq '.record.metrics'

# Measure LCP element on mobile via Playwright
npx playwright test --project=mobile-chrome --grep "LCP element"
```

---

## Related

- documentation/categories/monitoring/core-web-vitals-monitoring.md
- documentation/categories/monitoring/real-user-monitoring-rum.md
- documentation/categories/monitoring/frontend-real-user-monitoring-rum.md
- documentation/categories/monitoring/cloudflare-analytics-engine.md
- documentation/categories/monitoring/slo-error-budget-workers-pages.md

---

## Source URLs

- https://developers.cloudflare.com/speed/speed-test/
- https://web.dev/articles/vitals
- https://web.dev/articles/cls
- https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/fetchpriority
- https://developer.chrome.com/docs/crux/api/
