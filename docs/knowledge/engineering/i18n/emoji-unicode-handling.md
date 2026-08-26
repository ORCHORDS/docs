# emoji-unicode-handling

**Issue:** Handling emoji correctly in string operations, input, and display
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Emoji are multi-codepoint sequences. `.length`, `.slice()`, and character classes operate on code units, not emoji, causing truncation and broken characters.

## Pattern / Solution
```js
const msg = 'Hello, World!';

// WRONG: code-unit length
msg.length;

// CORRECT: grapheme count
[...new Intl.Segmenter().segment(msg)].length;

// Safe iteration
for (const { segment } of new Intl.Segmenter('en', { granularity: 'grapheme' }).segment(msg)) {
  console.log(segment);
}

// Safe truncate
function truncate(str, maxGraphemes) {
  const graphemes = [...new Intl.Segmenter().segment(str)];
  return graphemes.slice(0, maxGraphemes).map(g => g.segment).join('');
}
```
Family emoji example: single grapheme cluster composed of base emoji + ZWJ + more emoji = many code units.

## Gotchas
- DB VARCHAR(N) counting UTF-16 surrogates may truncate emoji mid-sequence
- Skin-tone modifiers (U+1F3FB-U+1F3FF) are separate codepoints paired with base emoji
- Regex `/./ ` with `u` flag matches codepoints, not graphemes

## Related
- `zero-width-joiner-sequences.md`
- `string-length-unicode.md`
- `grapheme-cluster-iteration.md`
