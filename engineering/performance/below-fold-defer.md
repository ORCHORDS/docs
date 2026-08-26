# below-fold-defer

**Issue:** Off-screen content and interactions load eagerly, competing with critical resources
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Resources, JavaScript, and components below the fold compete for bandwidth and CPU with above-fold content. Deferring them improves perceived and measured load performance.

## Pattern / Solution
1. Lazy-load below-fold images with loading=lazy.\n2. Use IntersectionObserver to load below-fold React components only when they approach the viewport.\n3. Defer below-fold analytics events until after TTI.\n4. Use import() for below-fold interactive components (comment sections, maps, chat).\n5. Prioritize critical resource loading by explicitly marking above-fold resources fetchpriority=high.

## Gotchas
- Too-aggressive deferral causes visible loading spinners as users scroll -- tune thresholds.\n- Server-rendered below-fold HTML still benefits from deferred JS hydration.\n- Search engine crawlers scroll pages; important SEO content should not require interaction to load.

## Related
above-fold-optimization, image-lazy-loading, intersection-observer-performance, code-splitting-strategies
