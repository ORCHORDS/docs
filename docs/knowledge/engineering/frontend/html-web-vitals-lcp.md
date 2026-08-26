# html-web-vitals-lcp

**Issue:** Largest Contentful Paint score is poor due to delayed hero image or font loading
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LCP element is a hero image that starts loading only after render; score is above 4 seconds on mobile.

## Pattern / Solution
```html
<!-- Preload the LCP image -->
<link rel="preload" as="image"  fetchpriority="high">

<!-- Or inline with fetchpriority -->
<img  fetchpriority="high" loading="eager" alt="Hero">
```

```tsx
// Next.js
<Image  priority alt="Hero" width={1200} height={630} />
```

```
LCP targets:
  Good:       <= 2.5s
  Needs work: 2.5s - 4.0s
  Poor:       > 4.0s
```

## Gotchas
- LCP is measured until the user first interacts; don't lazy-load the hero
- Server-side rendering improves LCP by sending HTML before JS executes
- Background images (CSS) are not discovered by the preload scanner; use <img> for LCP elements

## Related
- `html-performance-resource-hints.md`
- `next-js-image-optimization.md`
