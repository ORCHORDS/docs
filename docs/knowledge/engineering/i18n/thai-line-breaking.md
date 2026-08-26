# thai-line-breaking

**Issue:** Implementing correct line-breaking for Thai text (no word spaces)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Thai has no word separators. Browsers break lines at arbitrary boundaries by default, producing unreadable text.

## Pattern / Solution
CSS (modern browsers have built-in Thai dictionary):
```css
:lang(th) {
  word-break: normal;
  overflow-wrap: break-word;
  line-break: strict;
}
```
JavaScript with `Intl.Segmenter`:
```js
const seg = new Intl.Segmenter('th', { granularity: 'word' });
const words = [...seg.segment('สวัสดีชาวโลก')].map(s => s.segment);
// Inject zero-width space between words:
const html = words.join('\u200B');
```
Legacy: `wordcut` npm package via WASM.

## Gotchas
- `<wbr>` and `&shy;` require server-side segmentation
- Chrome's built-in Thai dictionary improves yearly; test across engine versions
- Myanmar and Khmer have the same no-space problem; `Intl.Segmenter` supports them

## Related
- `chinese-japanese-cjk-fonts.md`
- `grapheme-cluster-iteration.md`
