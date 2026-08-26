# real-user-monitoring-rum

**Issue:** Collecting performance metrics from real users' browsers to measure actual experience
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Synthetic tests show fast performance but users report slowness. Real network conditions and device capabilities differ from test environments.

## Pattern / Solution
Instrument with a RUM SDK (Datadog RUM, New Relic Browser, Sentry Performance, or custom via PerformanceObserver API). Collect LCP, INP, CLS, TTFB, FCP per page route. Sample at 10-20% for high-traffic sites. Tag with user cohort, device type, geography, and connection type. Build a p75 LCP dashboard segmented by page and geography. Alert when p75 LCP exceeds 2500ms sustained for 10min.

## Gotchas
RUM data is noisy — p50 is meaningless for tail latency; use p75 and p95. Bot traffic pollutes RUM — filter by human interaction signals. RUM agents add JavaScript bundle weight — use async loading. GDPR/CCPA implications: RUM collects user behavior data — include in privacy policy.

## Related
core-web-vitals-monitoring, funnel-analytics-monitoring, synthetic-monitoring-setup
