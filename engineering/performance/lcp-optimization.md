# lcp-optimization

**Issue:** Largest Contentful Paint exceeds 2.5s threshold
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LCP marks when the largest visible element (hero image, h1, background image) finishes rendering. Values above 4s are poor; 2.5-4s needs improvement.

## Pattern / Solution
1. Preload the LCP resource: `<link rel=preload as=image href=hero.webp fetchpriority=high>`.\n2. Eliminate render-blocking CSS/JS that delays the first paint.\n3. Serve the LCP image from the same origin or a preconnected CDN.\n4. Use fetchpriority=high on the img tag itself.\n5. Avoid lazy-loading the LCP image.\n6. Compress with WebP/AVIF; aim for < 100 KB.

## Gotchas
- Background CSS images are not preloadable without imagesrcset/imagesizes.\n- SSR cache misses spike TTFB, worsening LCP.\n- CrUX LCP differs from lab LCP; optimize for field data via origin summary.

## Related
core-web-vitals-overview, ttfb-optimization, image-optimization-webp, resource-hints-preload, above-fold-optimization
