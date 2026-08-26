# next-js-image-optimization

**Issue:** Unoptimized images cause LCP failures and large payload sizes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Hero images served as full-resolution JPEGs bloat the page and score poorly on Core Web Vitals.

## Pattern / Solution
```tsx
import Image from 'next/image';

// Fixed size (known dimensions)
<Image  width={1200} height={630} alt="Hero" priority />

// Fill parent container
<div style={{ position: 'relative', height: '400px' }}>
  <Image  fill style={{ objectFit: 'cover' }} alt="" />
</div>

// Remote images: configure domains in next.config.ts
const config = {
  images: {
    remotePatterns: [{ hostname: 'cdn.example.com' }],
  },
};
```

## Gotchas
- Add priority to LCP images to prevent preload warnings
- fill requires a positioned parent container
- alt="" for decorative images; meaningful alt for content images
- sizes prop required when using fill or responsive layouts for correct srcset

## Related
- `html-web-vitals-lcp.md`
- `html-srcset-responsive-images.md`
