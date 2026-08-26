# critical-css-extraction

**Issue:** Render-blocking stylesheets delay first paint
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A 200 KB stylesheet must fully download before the browser paints anything, causing 2-3 second white screens.

## Pattern / Solution
```html
<!-- Inline critical CSS in <head> -->
<style>
  /* Minimal above-the-fold styles only */
  body { margin: 0; font-family: system-ui; }
  .hero { min-height: 100vh; display: flex; }
</style>

<!-- Load full stylesheet asynchronously -->
<link rel="preload" as="style"  onload="this.rel='stylesheet'">
<noscript><link rel="stylesheet" ></noscript>
```

```bash
# Extract with critters (used by Angular CLI and Next.js)
npm install critters

# Or use critical npm package
npx critical index.html --inline --base dist/
```

## Gotchas
- Critical CSS must cover everything visible above the fold on first paint
- Inline critical CSS adds to HTML size; cache-busting loses the benefit of cached stylesheets
- Next.js and Vite handle this automatically for their built-in CSS; manual extraction for custom setups

## Related
- `html-web-vitals-lcp.md`
- `css-cascade-layers.md`
