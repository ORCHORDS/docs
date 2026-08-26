# lighthouse-scoring

**Issue:** Lighthouse score doesn't reflect real-user experience
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Lighthouse is a lab tool running in a simulated throttled environment. Its composite score guides optimization but can diverge from CrUX field data.

## Pattern / Solution
1. Run Lighthouse in CI with a stable, dedicated machine to reduce variance.\n2. Use --preset=desktop and --preset=mobile separately; optimize for mobile first.\n3. Compare Lighthouse scores against CrUX data in PageSpeed Insights.\n4. Use median of 3+ runs; single runs vary +/- 5-10 points.\n5. Focus on metric weights: LCP (25%), TBT (30%), CLS (25%), FCP (10%), SI (10%).

## Gotchas
- Lighthouse runs in Chrome; Safari/Firefox users may have different real-world experiences.\n- Throttling emulates a mid-range Android device; adjust if your audience differs.\n- A high Lighthouse score doesn't guarantee good CrUX -- real networks and devices vary wildly.

## Related
crux-field-data, pagespeed-insights-api, core-web-vitals-overview, rum-vs-synthetic-metrics
