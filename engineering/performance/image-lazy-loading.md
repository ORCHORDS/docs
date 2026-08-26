# image-lazy-loading

**Issue:** Off-screen images are loaded eagerly, wasting bandwidth
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Native lazy loading (loading=lazy) defers image fetches until they approach the viewport. Reduces initial page weight significantly for long pages.

## Pattern / Solution
1. Add loading=lazy to all below-fold img tags.\n2. Never add loading=lazy to LCP images -- they must load eagerly.\n3. Always set width and height attributes to prevent CLS when images load.\n4. Use decoding=async to avoid blocking the main thread during image decode.\n5. For JavaScript-rendered images, use IntersectionObserver as a fallback.

## Gotchas
- Browser-native lazy loading loads images ~1200px before they enter viewport.\n- loading=lazy on iframe also works for lazy-loading embedded content.\n- Lazy loading too aggressively causes images to load visibly as users scroll.

## Related
image-optimization-webp, responsive-images-srcset, intersection-observer-performance, above-fold-optimization
