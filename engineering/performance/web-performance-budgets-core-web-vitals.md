# Web Performance Budgets and Core Web Vitals Monitoring

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your product page scores 95 on Lighthouse but real users report
slow interactions — because INP (Interaction to Next Paint) is a
field-only metric that Lighthouse cannot measure. Your team
optimized LCP on the homepage but the product listing page (where
80% of traffic lands) still has a 4-second LCP. A third-party chat
widget added 200KB of JavaScript, blowing your bundle budget, but
nobody noticed because performance budgets are not enforced in CI.
Your CLS score spiked after a font change but the team only
discovered it from a drop in search rankings two weeks later.

## Context

Core Web Vitals (CWV) are Google's user-centric performance metrics
measured at the 75th percentile: LCP (Largest Contentful Paint)
<= 2.5s, INP (Interaction to Next Paint) <= 200ms, and CLS
(Cumulative Layout Shift) <= 0.1. INP replaced FID as the
responsiveness metric in March 2024 and is the most commonly failed
vital — roughly 43% of sites miss the 200ms threshold. Performance
budgets set explicit numeric limits (JS bundle size, page weight,
CWV targets) enforced in CI via Lighthouse CI. Effective monitoring
combines synthetic testing (lab) for regression catching with Real
User Monitoring (RUM) for actual user experience.

## Core Web Vitals thresholds

```
Metric   Good        Needs Improvement   Poor
──────────────────────────────────────────────────────────────
LCP      ≤ 2.5s      2.5s – 4.0s         > 4.0s
INP      ≤ 200ms     200ms – 500ms       > 500ms
CLS      ≤ 0.1       0.1 – 0.25          > 0.25

Measured at: 75th percentile of page visits
Segments: mobile and desktop separately
Source: Chrome User Experience Report (CrUX)

A URL/origin needs 75% of visits at "good" across
ALL THREE metrics to pass CWV assessment.
```

## INP optimization

```
INP measures the worst interaction latency across a page visit.
It is a pure FIELD (RUM) metric — lab tools like Lighthouse
cannot measure it. Lighthouse's Total Blocking Time (TBT) is
the lab proxy that correlates with INP.

Optimization strategies:

  1. Break up long tasks (>50ms blocking main thread)
     → scheduler.yield() — Chrome 2024+, Firefox Aug 2025
       Returns a promise, places continuation in higher-priority
       queue than newly scheduled tasks
     → setTimeout(fn, 0) as fallback
     → requestIdleCallback for non-urgent work

  2. Debounce/defer non-critical JS execution

  3. Minimize work inside event handlers
     → Move heavy computation to Web Workers
     → Defer non-visual updates with requestAnimationFrame

  4. Reduce DOM size
     → content-visibility: auto for off-screen content
     → Virtualize long lists (react-window, TanStack Virtual)

  5. Minimize third-party script impact
     → Defer/async load chat widgets, analytics
     → Use Partytown to offload to Web Worker
```

## LCP optimization

```
LCP measures when the largest content element renders.

  Common LCP elements: hero images, heading text, video posters

  Optimization:
    → Preload LCP resource: <link rel="preload" as="image">
    → fetchpriority="high" on the LCP image
    → Avoid render-blocking CSS/JS before LCP
    → Use CDN for static assets
    → Modern image formats: AVIF > WebP > JPEG
    → Optimize server response time (TTFB)
    → Inline critical CSS, defer non-critical

  Common mistake: optimizing only the homepage LCP while
  the high-traffic product/listing page has a 4s LCP.
```

## CLS debugging

```
CLS measures unexpected visual shifts during page load.

  Common causes and fixes:

    Images without dimensions:
      → Always set width/height or aspect-ratio on <img>

    Injected content above fold:
      → Reserve space for ads, banners, embeds
      → Use min-height on container elements

    Font loading shifts (FOIT/FOUT):
      → font-display: optional (prevents shift entirely)
      → Size-adjust fallback fonts to match web font metrics

    Dynamic content insertion:
      → Animate with transform (not top/left/margin)
      → Use position: absolute for overlays
```

## Performance budgets

```
Budget type          Example target
──────────────────────────────────────────────────────────────
JS bundle size       ≤ 170KB gzipped (main bundle)
Total page weight    ≤ 1-2MB (including images)
Image weight         ≤ 500KB per page
LCP                  ≤ 2.5s
INP (via TBT proxy)  TBT ≤ 200ms
CLS                  ≤ 0.1
Performance score    ≥ 90 (Lighthouse)

Enforcement:
  → CI gate: fail build if budget exceeded
  → PR comment: show delta from baseline
  → Alert: notify team on regression
```

## Lighthouse CI configuration

```json
// lighthouserc.json
{
  "ci": {
    "collect": {
      "url": ["http://localhost:3000/", "http://localhost:3000/products"],
      "numberOfRuns": 3
    },
    "assert": {
      "assertions": {
        "categories:performance": ["error", { "minScore": 0.9 }],
        "first-contentful-paint": ["warn", { "maxNumericValue": 2000 }],
        "largest-contentful-paint": ["error", { "maxNumericValue": 2500 }],
        "total-blocking-time": ["error", { "maxNumericValue": 200 }],
        "cumulative-layout-shift": ["error", { "maxNumericValue": 0.1 }],
        "resource-summary:script:size": ["error", { "maxNumericValue": 300000 }]
      }
    }
  }
}
```

## Monitoring: RUM vs synthetic

```
Type        Tool                    Measures
──────────────────────────────────────────────────────────────
Synthetic   Lighthouse CI           Lab metrics (controlled)
            WebPageTest             Filmstrip, waterfall
            Calibre, SpeedCurve     Continuous + budget alerts

RUM         web-vitals library      Real user CWV (field)
            CrUX (Chrome UX         Google's authoritative
            Report)                 field data for Search
            Datadog RUM,            Full session replay +
            New Relic Browser       performance correlation

Best practice: combine both
  Synthetic: catch regressions before deploy (CI gate)
  RUM: track real-world impact and prioritize fixes

CrUX is the authoritative source for Core Web Vitals
pass/fail status used in Google Search ranking signals.
```

```javascript
// web-vitals library — send RUM data to analytics
import { onLCP, onINP, onCLS } from 'web-vitals';

function sendToAnalytics(metric) {
  navigator.sendBeacon('/analytics', JSON.stringify({
    name: metric.name,
    value: metric.value,
    id: metric.id,
    rating: metric.rating,
  }));
}

onLCP(sendToAnalytics);
onINP(sendToAnalytics);
onCLS(sendToAnalytics);
```

## Anti-patterns

- **Optimizing only lab scores** — Lighthouse score of 95 with
  poor field CWV means real users on real devices have a different
  experience. Monitor RUM alongside synthetic.
- **Ignoring INP because Lighthouse doesn't report it** — INP is
  field-only and the most commonly failed vital. Use TBT as the
  lab proxy and web-vitals library for field measurement.
- **One-time performance audits** — without CI-gated budgets,
  regressions creep in with every dependency update and feature
  addition. Enforce budgets on every PR.
- **Measuring only the homepage** — product pages, listing pages,
  and checkout flows often have worse performance than the homepage.
  Budget and monitor all key page templates.

## Gotchas

- **Third-party scripts are budget killers** — ads, analytics,
  chat widgets, and social embeds can silently blow INP/TBT
  budgets. Audit third-party impact separately.
- **scheduler.yield() browser support** — available in Chrome
  (2024) and Firefox (August 2025), not yet in Safari. Use
  progressive enhancement with setTimeout fallback.
- **CrUX data has a 28-day rolling window** — changes to
  performance take up to 28 days to reflect in CrUX data.
  Use RUM for immediate feedback.
- **Lighthouse scores vary between runs** — run multiple times
  (3-5) and use the median. Single-run scores are unreliable
  for CI assertions.

## Verification

- Performance budgets defined for JS size, page weight, and CWV.
- Lighthouse CI configured to gate PRs on budget assertions.
- web-vitals library deployed for real user monitoring.
- INP optimized via long task breaking and scheduler.yield().
- LCP resource preloaded with fetchpriority="high".
- CLS prevented with explicit image dimensions and font handling.
- All key page templates monitored, not just homepage.

## Related

- `documentation/categories/performance/critical-rendering-path-css-optimization.md`
- `documentation/categories/performance/image-optimization-avif-webp.md`
- `documentation/categories/frontend/react-19-server-components-streaming-ssr.md`

## Source URLs (verified 2026-08-16)

- Web Vitals — https://web.dev/articles/vitals
- Defining Core Web Vitals Thresholds — https://web.dev/articles/defining-core-web-vitals-thresholds
- Using scheduler.yield — https://developer.chrome.com/blog/use-scheduler-yield
- Optimize Long Tasks — https://web.dev/articles/optimize-long-tasks
