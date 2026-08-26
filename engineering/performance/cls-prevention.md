# cls-prevention

**Issue:** Cumulative Layout Shift score exceeds 0.1
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CLS sums unexpected layout shifts weighted by impact x distance fractions. Common culprits: images without dimensions, late-injected ads, web fonts causing FOUT, dynamic banners.

## Pattern / Solution
1. Always set explicit width and height on img and video elements.\n2. Reserve space for ads/embeds with CSS min-height or aspect-ratio containers.\n3. Use font-display: optional or preload fonts to avoid FOUT shifts.\n4. Animate with transform and opacity only; avoid top/left/margin changes.\n5. Insert new DOM above the fold only in response to user gestures.

## Gotchas
- Back/forward cache restores can replay shifts; test with BFCache disabled.\n- Infinite scroll that shifts anchored content fails CLS even if intentional.\n- Chrome DevTools Layout Shift track in Performance panel shows per-shift scores.

## Related
core-web-vitals-overview, font-display-swap, css-animation-gpu, above-fold-optimization
