# speed-index-optimization

**Issue:** Speed Index is high, indicating slow visual progress during page load
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Speed Index measures how quickly the visible content of a page is visually populated. A lower score means content appears faster. It is a Lighthouse metric weighted at 10% of the performance score.

## Pattern / Solution
1. Reduce main thread work that blocks rendering: defer non-critical JS.\n2. Eliminate render-blocking resources in the critical path.\n3. Inline critical CSS to enable immediate above-fold rendering.\n4. Optimize server response time (TTFB) to start rendering earlier.\n5. Use server-side rendering or static generation to deliver pre-rendered HTML.

## Gotchas
- Speed Index is a composite visual metric; improving FCP and LCP typically improves it.\n- Speed Index is calculated from a video of the page loading; it is more expensive to compute than other metrics.\n- A fast Speed Index does not guarantee good INP; also optimize interactivity.

## Related
first-contentful-paint, lcp-optimization, above-fold-optimization, lighthouse-scoring
