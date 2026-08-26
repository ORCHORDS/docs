# critical-rendering-path

**Issue:** Browser cannot paint until render-blocking resources complete
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The CRP is the sequence: HTML parse then CSSOM build then Render Tree then Layout then Paint. Any blocking CSS or synchronous JS in head stalls the entire pipeline.

## Pattern / Solution
1. Inline critical CSS (above-fold styles) in style tags; load full CSS asynchronously.\n2. Mark all non-critical scripts defer or async.\n3. Reduce CRP depth: minimize the number of resources required before first paint.\n4. Use link rel=preload to fetch critical resources in parallel with HTML parsing.\n5. Move render-blocking scripts to the end of body if defer is not possible.

## Gotchas
- async scripts execute as soon as downloaded, potentially blocking paint; prefer defer for ordered execution.\n- CSS @import creates serial chains; use link tags instead.\n- Fonts block rendering if text is not displayed; use font-display: swap or optional.

## Related
render-blocking-resources, first-contentful-paint, above-fold-optimization, font-display-swap
