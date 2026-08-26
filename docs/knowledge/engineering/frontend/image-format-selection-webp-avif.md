# image-format-selection-webp-avif

**Issue:** JPEG/PNG images are 3-5x larger than equivalent WebP/AVIF images
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Product images account for 60% of page weight; switching to modern formats would cut load times significantly.

## Pattern / Solution
```html
<!-- Picture with format fallback -->
<picture>
  <source type="image/avif" srcset="photo.avif">
  <source type="image/webp" srcset="photo.webp">
  <img  alt="Product" width="800" height="600">
</picture>
```

```
Format comparison for a 1MB JPEG:
  JPEG    1000 KB  baseline
  WebP     400 KB  60% smaller, supported in all modern browsers
  AVIF     250 KB  75% smaller, Chrome 85+, Firefox 93+, Safari 16+
  JPEG XL  300 KB  similar to AVIF, limited browser support (2026)

Use cases:
  Photos       -> AVIF > WebP > JPEG
  Transparency -> WebP (lossy) or PNG (lossless)
  Animation    -> WebP or video (MP4/WebM)
  Icons/logos  -> SVG
```

## Gotchas
- AVIF encoding is slow; pre-generate at build time, not on-the-fly
- Sharp npm package handles WebP/AVIF conversion in Node.js
- Squoosh CLI for batch conversion: `squoosh-cli --avif '{}' *.jpg`

## Related
- `html-srcset-responsive-images.md`
- `html-lazy-loading-images.md`
