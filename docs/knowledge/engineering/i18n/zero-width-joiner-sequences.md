# zero-width-joiner-sequences

**Issue:** Understanding Zero Width Joiner (ZWJ) sequences used in emoji and script rendering
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ZWJ (U+200D) combines adjacent codepoints into a single visual unit. Incorrectly splitting or filtering ZWJ sequences breaks display.

## Pattern / Solution
Common sequences:
```
Woman technologist: U+1F469 + ZWJ U+200D + U+1F4BB
Rainbow flag: U+1F3F3 + VS16 + ZWJ + U+1F308
```
Detect ZWJ:
```js
const hasZWJ = (s) => s.includes('\u200D');
```
Always use grapheme segmentation when splitting:
```js
const seg = new Intl.Segmenter('en', { granularity: 'grapheme' });
[...seg.segment('Hello')].map(g => g.segment);
```

## Gotchas
- ZWJ is also used in Arabic and Sinhala for conjunct shaping; do not filter globally
- Canvas and SVG rendering engines may not support all ZWJ sequences
- Social platforms render only a subset of approved ZWJ sequences

## Related
- `emoji-unicode-handling.md`
- `grapheme-cluster-iteration.md`
