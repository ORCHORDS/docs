# above-fold-optimization

**Issue:** Content visible on initial viewport load is slow to render
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Above-fold content is what users see before scrolling. Optimizing it directly improves FCP and LCP. Everything not visible on load can be deferred.

## Pattern / Solution
1. Inline critical CSS for above-fold styles; async-load full stylesheet.\n2. Preload the LCP image with fetchpriority=high.\n3. Server-render or static-generate above-fold HTML.\n4. Avoid lazy-loading any above-fold images or components.\n5. Minimize JavaScript required to make above-fold content interactive.

## Gotchas
- Above the fold varies by device; test on the most common viewport sizes in your analytics.\n- Over-inlining CSS increases HTML size; target < 15 KB of inlined critical CSS.\n- Client-rendered SPAs have poor above-fold performance without SSR/SSG.

## Related
first-contentful-paint, lcp-optimization, critical-rendering-path, below-fold-defer
