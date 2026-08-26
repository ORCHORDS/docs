# pagespeed-insights-api

**Issue:** Manually checking PageSpeed Insights doesn't scale
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PageSpeed Insights (PSI) API combines CrUX field data with Lighthouse lab data in one API call. Useful for automated monitoring, dashboards, and CI gates.

## Pattern / Solution
1. Endpoint: https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=URL&strategy=mobile&key=KEY.\n2. Parse lighthouseResult.categories.performance.score for Lighthouse score.\n3. Parse loadingExperience.metrics for CrUX data.\n4. Automate daily runs and alert on score drops > 5 points.\n5. Use origin parameter for origin-level CrUX without running Lighthouse.

## Gotchas
- Free tier: 25,000 queries/day; enable billing for higher limits.\n- API responses vary +/- 5 points; use median of 3 calls or accept the variance.\n- PSI does not support authenticated pages; use Lighthouse CI for behind-login flows.

## Related
crux-field-data, lighthouse-scoring, performance-regression-detection, performance-dashboard-design
