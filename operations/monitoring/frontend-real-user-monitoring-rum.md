# Frontend Real User Monitoring (RUM)

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your frontend performance monitoring relies on synthetic tests (Lighthouse
CI, WebPageTest) that measure performance from a lab environment. Real
users on slow networks, old devices, and diverse geographies experience
worse performance than your synthetic scores suggest. You have no
visibility into actual user experience — page load times, interaction
latency, and client-side errors — segmented by device, browser, geography,
and connection quality.

## Context

Real User Monitoring (RUM) collects performance and error data from actual
user sessions in production, providing visibility into real-world
experience that synthetic monitoring cannot replicate. RUM captures Core
Web Vitals (LCP, CLS, INP), client-side errors, network conditions, and
user interactions across all devices and browsers. In 2026, INP
(Interaction to Next Paint) has fully replaced FID as the interactivity
metric in Core Web Vitals.

## Core Web Vitals (2026)

| Metric | Full name | Good | Needs improvement | Poor |
|---|---|---|---|---|
| **LCP** | Largest Contentful Paint | < 2.5s | 2.5-4.0s | > 4.0s |
| **CLS** | Cumulative Layout Shift | < 0.1 | 0.1-0.25 | > 0.25 |
| **INP** | Interaction to Next Paint | < 200ms | 200-500ms | > 500ms |

## RUM tool landscape (2026)

### Full-stack observability platforms

| Tool | Key strengths | Session replay | Pricing model |
|---|---|---|---|
| **Datadog RUM** | Backend correlation, APM traces | Yes | Per 1K sessions |
| **New Relic Browser** | Full-stack correlation, NRQL queries | Yes | Per GB ingested |
| **Dynatrace RUM** | AI root cause (Davis), SPA support | Yes | Per session |

### Frontend-focused tools

| Tool | Key strengths | Session replay | Pricing model |
|---|---|---|---|
| **Sentry Performance** | Error tracking + performance | Yes | Per event |
| **SpeedCurve** | Performance budgets, filmstrip view | No | Subscription |
| **Elastic RUM** | Open source, self-hosted option | Limited | Per node / cloud |

### Open source / self-hosted

| Tool | Key strengths |
|---|---|
| **web-vitals.js** | Google's library for collecting Core Web Vitals metrics |
| **OpenTelemetry Browser** | OTel SDK for browser instrumentation |
| **Plausible/Umami** | Privacy-focused analytics with basic performance data |

## Implementation

### Collecting Core Web Vitals with web-vitals.js

```javascript
import { onLCP, onCLS, onINP } from 'web-vitals';

function sendMetric(metric) {
  navigator.sendBeacon('/analytics', JSON.stringify({
    name: metric.name,
    value: metric.value,
    rating: metric.rating,    // 'good' | 'needs-improvement' | 'poor'
    delta: metric.delta,
    id: metric.id,
    navigationType: metric.navigationType,
    url: location.href,
    userAgent: navigator.userAgent,
  }));
}

onLCP(sendMetric);
onCLS(sendMetric);
onINP(sendMetric);
```

### SPA (Single Page Application) considerations

SPAs require soft navigation tracking — page transitions that don't trigger
a full page load. In 2026, the experimental Soft Navigation API provides
native browser support, but most RUM tools implement their own SPA route
change detection.

```javascript
// Custom SPA route change tracking
const observer = new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (entry.entryType === 'soft-navigation') {
      sendMetric({
        name: 'soft-navigation',
        value: entry.startTime,
        url: entry.name,
      });
    }
  }
});
observer.observe({ type: 'soft-navigation', buffered: true });
```

## Key dimensions for segmentation

Aggregate RUM metrics are misleading. Segment by:

- **Device type** — mobile vs. desktop vs. tablet.
- **Connection quality** — 4G, 3G, slow-2g (via `navigator.connection`).
- **Geography** — country/region.
- **Browser** — Chrome, Safari, Firefox, and their versions.
- **Page type** — landing page, product page, checkout.
- **User cohort** — new vs. returning, free vs. paid.

## Anti-patterns

- **Synthetic only** — Lighthouse scores are useful for CI gates but don't
  represent real user experience. A site scoring 95 in Lighthouse can
  still have poor real-user INP if JavaScript execution on real devices is
  slow.
- **Aggregate-only metrics** — a p50 LCP of 2.0s hides a p95 of 8.0s.
  Track p50, p75, and p95 percentiles.
- **No error tracking** — RUM without client-side error tracking misses
  JavaScript exceptions that break user flows silently.
- **Sampling too aggressively** — sampling below 10% loses visibility into
  edge cases and rare pages. Start at 100% and reduce only when volume
  demands it.
- **Ignoring mobile** — mobile users often represent 50-70% of traffic
  and experience worse performance. Separate mobile and desktop metrics.

## Gotchas

- **Third-party scripts** — ad tags, analytics, chat widgets, and social
  embeds degrade Core Web Vitals but are outside your control. Use RUM
  data to quantify their impact and negotiate with vendors.
- **INP attribution** — a poor INP score tells you interactions are slow
  but not which interaction or why. Use the `PerformanceEventTiming` API
  and long-task attribution to identify the specific handler.
- **Privacy regulations** — session replay collects user interactions
  that may include personal data. Mask form inputs, redact PII, and
  ensure compliance with GDPR/CCPA consent requirements.
- **Data volume** — RUM generates significant data volume at scale. A site
  with 1M daily users at 100% sampling produces ~3M metric events per day.
  Set retention policies and sampling rates to control costs.
- **Bot traffic** — filter bot traffic from RUM data. Bots don't
  represent real user experience and skew metrics.

## Verification

- Core Web Vitals (LCP, CLS, INP) are collected from real users and
  visible on a dashboard.
- Metrics are segmented by device type, geography, and connection quality.
- p75 Core Web Vitals meet "good" thresholds (LCP < 2.5s, CLS < 0.1,
  INP < 200ms).
- Client-side errors are tracked and triaged.
- Performance budgets are enforced in CI (synthetic) and monitored in
  production (RUM).
- Session replay respects privacy regulations — PII is masked.

## Related

- `documentation/categories/performance/core-web-vitals-optimization.md`
- `documentation/categories/frontend/performance-optimization.md`
- `documentation/categories/monitoring/golden-signals-monitoring.md`
- `documentation/categories/monitoring/opentelemetry-collector-pipelines.md`

## Source URLs (verified 2026-08-16)

- web-vitals.js — https://github.com/GoogleChrome/web-vitals
- Better Stack RUM comparison — https://betterstack.com/community/comparisons/real-user-monitoring-tools/
- Middleware RUM tools — https://middleware.io/blog/real-user-monitoring-tools/
- Dynatrace RUM — https://www.dynatrace.com/news/blog/unprecedented-insights-into-frontend-user-experience-with-dynatrace-real-user-monitoring/
