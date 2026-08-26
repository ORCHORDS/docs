# responsive-images-srcset

**Issue:** Single image size served regardless of device screen width
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A 2000px image served to a 375px mobile screen wastes 4-8x bandwidth. srcset and sizes attributes let browsers choose the optimal image resolution.

## Pattern / Solution
1. Generate multiple sizes: 400w, 800w, 1200w, 1600w.\n2. Add srcset: img srcset=img-400.webp 400w, img-800.webp 800w sizes=(max-width: 600px) 100vw, 50vw.\n3. Use sizes accurately -- browsers use it to select the source before layout.\n4. Automate with CDN image transformation.\n5. Use picture for art direction (different crops at different viewports).

## Gotchas
- sizes must reflect the CSS layout width at each breakpoint; inaccurate sizes defeats the optimization.\n- DPR also affects selection; a 2x screen downloads the 2x larger image.\n- Generating many sizes at build time is slow; CDN on-demand resizing is faster to implement.

## Related
image-optimization-webp, image-lazy-loading, lcp-optimization
