# html-srcset-responsive-images

**Issue:** Serving full-resolution images to mobile devices wastes bandwidth and hurts performance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A 2400px wide hero image is served to a 375px mobile screen, downloading 10x more pixels than needed.

## Pattern / Solution
```html
<!-- Resolution switching -->
<img
  srcset="hero-400.webp 400w, hero-800.webp 800w, hero-1600.webp 1600w"
  sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 800px"

  alt="Hero"
  width="800" height="450"
>

<!-- Art direction with picture -->
<picture>
  <source media="(max-width: 640px)" srcset="hero-mobile.webp" type="image/webp">
  <source media="(min-width: 641px)" srcset="hero-desktop.webp" type="image/webp">
  <img  alt="Hero" width="1200" height="630">
</picture>
```

## Gotchas
- sizes must describe the rendered width, not the container width
- src is the fallback for browsers that do not support srcset
- WebP/AVIF source in <picture> with JPEG fallback in <img>

## Related
- `html-lazy-loading-images.md`
- `image-format-selection-webp-avif.md`
