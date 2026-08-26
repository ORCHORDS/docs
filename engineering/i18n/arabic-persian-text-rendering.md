# arabic-persian-text-rendering

**Issue:** Correctly rendering Arabic and Persian text in web UIs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Arabic and Persian use the Arabic script in RTL. Character shaping (connected letterforms) fails with wrong fonts or missing Unicode isolation.

## Pattern / Solution
```html
<html lang="ar" dir="rtl">
<span lang="fa" dir="rtl">متن فارسی</span>
```
Font stack:
```css
body { font-family: 'Noto Naskh Arabic', 'Scheherazade New', Arial, sans-serif; }
```
Persian digits (U+06F0-U+06F9):
```js
const toPersian = (n) => n.toString().replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
```
Bidirectional isolation for embedded LTR content:
```html
<bdi>user@example.com</bdi>
```

## Gotchas
- Do not mix `unicode-bidi: embed` with `dir` attribute; use one method consistently
- Kashida justification requires `text-justify: kashida` -- limited browser support
- Arabic numbers in CSS counters require `list-style-type: arabic-indic`

## Related
- `bidi-rtl-layout-css.md`
- `bidi-algorithm-unicode.md`
