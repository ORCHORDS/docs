# html-lazy-loading-images

**Issue:** Off-screen images load on page load, wasting bandwidth on content the user may never see
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A page with 50 product images sends 8 MB of image data on first load even though only 6 images are visible.

## Pattern / Solution
```html
<!-- Native lazy loading -->
<img  loading="lazy" width="400" height="300" alt="Product">

<!-- Eager load above-the-fold images -->
<img  loading="eager" fetchpriority="high" alt="Hero">

<!-- Next.js Image component handles this automatically -->
<Image  width={400} height={300} alt="Product" />
<!-- loading="lazy" is the default; add priority for above-fold -->
```

## Gotchas
- Do not lazy-load images in the first viewport; it delays LCP
- loading="lazy" requires width and height to avoid CLS
- The browser decides the threshold (~1200px below viewport on Chrome); it is not configurable
- Use Intersection Observer for finer control or for background images

## Related
- `html-web-vitals-lcp.md`
- `browser-intersection-observer.md`
