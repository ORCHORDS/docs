# performance-dashboard-design

**Issue:** Performance data is scattered and hard to act on
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A performance dashboard consolidates Core Web Vitals, server metrics, and business impact in one place. Without it, performance data is siloed in separate tools and teams don't see the full picture.

## Pattern / Solution
1. Show CrUX p75 for LCP, INP, CLS by URL and device type.\n2. Overlay deployments to correlate changes with metric shifts.\n3. Include business metrics (conversion rate, bounce rate) alongside web vitals.\n4. Add server-side metrics: TTFB, error rate, DB query time.\n5. Use Grafana with a PostgreSQL or BigQuery datasource for CrUX API data.

## Gotchas
- Dashboards without alerting are reviewed only when problems are already known.\n- CrUX data has a 28-day lag; synthetic monitoring provides faster feedback.\n- Vanity metrics (overall Lighthouse score) can hide page-specific regressions; track individual URLs.

## Related
crux-field-data, rum-vs-synthetic-metrics, pagespeed-insights-api, performance-regression-detection
