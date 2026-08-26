# image-optimization-webp

**Issue:** Images are served in JPEG/PNG instead of modern formats
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
WebP reduces file size 25-35% vs. JPEG at equivalent quality. AVIF reduces 50% vs. JPEG. Images are typically the largest assets on a page by transfer size.

## Pattern / Solution
1. Convert images to WebP/AVIF at build time with Sharp, Squoosh, or cwebp.\n2. Use picture with format fallbacks: source srcset=img.avif, source srcset=img.webp, img src=img.jpg.\n3. Use CDN image transformation (Cloudflare Images, Imgix) for automatic format selection.\n4. Set quality 75-85 for photos; lossless for graphics with text.\n5. Serve responsive sizes with srcset.

## Gotchas
- AVIF encode time is much higher than WebP; pre-generate at build time.\n- Safari added AVIF support in Safari 16; check your user's browser distribution.\n- Animated WebP replaces GIF but AVIF is better for animated content too.

## Related
image-lazy-loading, responsive-images-srcset, lcp-optimization
