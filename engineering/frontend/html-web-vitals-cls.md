# html-web-vitals-cls

**Issue:** Layout shifts during load cause poor CLS scores and disorienting UX
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Ads, images without dimensions, or late-loading fonts shift content after the page appears stable.

## Pattern / Solution
```html
<!-- Always set width and height on images -->
<img  width="800" height="600" alt="">

<!-- Reserve space for ads -->
<div style="min-height: 250px;">
  <AdUnit />
</div>

<!-- Font: font-display: optional avoids swap CLS -->
@font-face {
  font-family: 'Inter';
  src: url('/fonts/Inter.woff2') format('woff2');
  font-display: optional;
}
```

```
CLS targets:
  Good:       <= 0.1
  Needs work: 0.1 - 0.25
  Poor:       > 0.25
```

## Gotchas
- Animations that move elements trigger CLS unless using transform
- Injecting content above existing content is a major CLS source
- Use aspect-ratio CSS property instead of padding-top hack for responsive embeds

## Related
- `html-web-vitals-lcp.md`
- `css-animation-performance.md`
