# font-loading-optimization

**Issue:** Web fonts block rendering or cause invisible text and layout shift
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Text is invisible for 3 seconds (FOIT) on slow connections while the font downloads.

## Pattern / Solution
```css
@font-face {
  font-family: 'Inter';
  src: url('/fonts/inter.woff2') format('woff2');
  font-display: swap;     /* show fallback immediately, swap when loaded */
  font-weight: 400 700;   /* variable font range */
  unicode-range: U+0000-00FF; /* subset for Latin only */
}
```

```html
<!-- Preload critical fonts -->
<link rel="preload" as="font"  type="font/woff2" crossorigin>
```

```
font-display values:
  auto     - browser default (usually block)
  block    - invisible for ~3s then swap (FOIT)
  swap     - fallback immediately, swap when ready (FOUT but no FOIT)
  fallback - 100ms block then swap; no swap after 3s
  optional - 100ms block; no swap (best for CLS)
```

## Gotchas
- Subsetting fonts with glyphhanger or pyftsubset reduces size by 80%+
- Variable fonts replace multiple weight files with one file
- next/font handles all of this automatically for Next.js apps

## Related
- `next-js-font-optimization.md`
- `html-web-vitals-cls.md`
