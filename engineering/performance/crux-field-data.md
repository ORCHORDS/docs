# crux-field-data

**Issue:** CrUX data shows poor Core Web Vitals despite good lab scores
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Chrome UX Report (CrUX) aggregates real-user measurements from Chrome browsers. It powers Google Search ranking signals. Lab tools like Lighthouse may show green while CrUX shows red.

## Pattern / Solution
1. Access CrUX via PageSpeed Insights, CrUX API (free), or BigQuery for historical analysis.\n2. Filter by device type (phone vs. desktop) to find platform-specific issues.\n3. Look at the p75 value for each metric -- Google uses p75 for thresholds.\n4. Compare origin-level vs. URL-level data; a single slow page can drag the origin.\n5. Investigate user segments: slow networks, low-end devices, specific geographies.

## Gotchas
- CrUX data has a 28-day rolling window; improvements take weeks to reflect.\n- Origins with low traffic may not appear in CrUX (requires ~1000 users/month minimum).\n- CrUX does not capture all browsers -- only opted-in Chrome users.

## Related
lighthouse-scoring, pagespeed-insights-api, rum-vs-synthetic-metrics, performance-dashboard-design
