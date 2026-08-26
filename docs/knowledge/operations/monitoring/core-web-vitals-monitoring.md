# core-web-vitals-monitoring

**Issue:** Tracking Google's Core Web Vitals (LCP, INP, CLS) for SEO and user experience
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Google Search Console flags poor Core Web Vitals. Pages fail CWV thresholds, affecting SEO rankings.

## Pattern / Solution
Measure three metrics: LCP (Largest Contentful Paint) — good under 2.5s; INP (Interaction to Next Paint) — good under 200ms; CLS (Cumulative Layout Shift) — good under 0.1. Collect via RUM using PerformanceObserver or the web-vitals npm package. Report to analytics pipeline per URL and percentile. Track in Google Search Console. Alert when field data p75 exceeds good threshold for more than 10% of pages.

## Gotchas
INP replaced FID in March 2024 — update tooling. CLS is measured over the entire page lifecycle — late layout shifts from lazy-loaded images are common culprits. LCP differs between mobile and desktop — track separately. Lab data and field data diverge significantly — field data is authoritative for SEO.

## Related
real-user-monitoring-rum, funnel-analytics-monitoring, synthetic-monitoring-setup
