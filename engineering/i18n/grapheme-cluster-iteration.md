# grapheme-cluster-iteration

**Issue:** Iterating over user-perceived characters (grapheme clusters) in a Unicode string
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`for...of` iterates codepoints; `.split('')` iterates UTF-16 code units. Neither matches what a user sees as "one character" when combining marks or ZWJ sequences are present.

## Pattern / Solution
Using `Intl.Segmenter` (ES2022):
```js
const text = 'Devanagari text';

const seg = new Intl.Segmenter('hi', { granularity: 'grapheme' });
const graphemes = [...seg.segment(text)].map(g => g.segment);

// Correctly reverse a string
const reverse = (s) =>
  [...new Intl.Segmenter().segment(s)].map(g => g.segment).reverse().join('');
```
Word segmentation:
```js
const wordSeg = new Intl.Segmenter('en', { granularity: 'word' });
[...wordSeg.segment('Hello, world!')].filter(s => s.isWordLike).map(s => s.segment);
// -> ['Hello', 'world']
```

## Gotchas
- `Intl.Segmenter` requires Node 16+ or modern browsers; polyfill with `graphemer` npm package
- Sentence segmentation (`granularity: 'sentence'`) is language-dependent and less accurate
- Locale is advisory for grapheme/word but significant for sentence boundaries

## Related
- `string-length-unicode.md`
- `emoji-unicode-handling.md`
- `thai-line-breaking.md`
