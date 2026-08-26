# resource-hints-preload

**Issue:** Critical resources discovered too late in the loading sequence
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
link rel=preload instructs the browser to fetch a resource at high priority as soon as possible, before the normal discovery order.

## Pattern / Solution
1. Preload LCP image: link rel=preload as=image href=hero.webp fetchpriority=high.\n2. Preload critical fonts: link rel=preload as=font type=font/woff2 href=... crossorigin.\n3. Preload key scripts needed for interactivity.\n4. Add fetchpriority=high for the single most important resource.\n5. Use imagesrcset and imagesizes for responsive image preloading.

## Gotchas
- Preloading resources not used within 3 seconds triggers a browser console warning.\n- crossorigin attribute is required for font preloads even for same-origin fonts.\n- Preloading too many resources competes for bandwidth and hurts overall load time.

## Related
lcp-optimization, font-preloading, network-waterfall-analysis, above-fold-optimization
