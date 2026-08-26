# webpagetest-patterns

**Issue:** Need deeper waterfall and filmstrip analysis than Lighthouse provides
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
WebPageTest (WPT) offers multi-step scripting, real device testing, visual comparisons, and connection waterfall analysis that Lighthouse cannot replicate.

## Pattern / Solution
1. Use the WPT API for automated testing.\n2. Enable Capture video to get filmstrip and Speed Index.\n3. Use connection view to identify render-blocking chains.\n4. Compare repeat views to diagnose caching effectiveness.\n5. Use Script feature to test authenticated flows.

## Gotchas
- WPT servers are shared; results vary by server load. Use private instances for CI.\n- The Opportunities tab suggests optimizations but doesn't account for your stack.\n- SPOF test blocks third-party domains to reveal their performance impact.

## Related
network-waterfall-analysis, lighthouse-scoring, rum-vs-synthetic-metrics, chrome-devtools-network
