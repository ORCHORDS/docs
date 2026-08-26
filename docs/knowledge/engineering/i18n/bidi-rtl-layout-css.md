# bidi-rtl-layout-css

**Issue:** Flipping UI layout for RTL languages using CSS logical properties
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CSS physical properties (`margin-left`, `padding-right`, `float: left`) do not flip automatically for RTL. Logical properties adapt to text direction.

## Pattern / Solution
```html
<html lang="ar" dir="rtl">
```
Replace physical with logical:
```css
/* Physical (avoid) */
.card { margin-left: 16px; padding-right: 8px; float: left; text-align: left; }

/* Logical (RTL-safe) */
.card {
  margin-inline-start: 16px;
  padding-inline-end: 8px;
  float: inline-start;
  text-align: start;
}
```
Flexbox auto-mirrors in RTL. For transforms:
```css
.arrow-icon { transform: scaleX(var(--dir-flip, 1)); }
[dir="rtl"] .arrow-icon { --dir-flip: -1; }
```

## Gotchas
- `border-left` has no logical equivalent before `border-inline-start` (Safari 15+)
- `position: absolute; left: 0` is still physical -- use `inset-inline-start`
- Flexbox `row-reverse` does not further flip for RTL

## Related
- `rtl-safe-component-patterns.md`
- `arabic-persian-text-rendering.md`
- `hebrew-rtl-react.md`
