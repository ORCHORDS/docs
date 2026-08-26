# string-length-unicode

**Issue:** Computing the correct visual length of a Unicode string for truncation and validation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
JavaScript `.length` returns UTF-16 code unit count. Emoji require 2 code units (surrogate pairs), inflating the count. DB VARCHAR limits count differently again.

## Pattern / Solution
```js
const s = 'Wave and Hello';

s.length;                         // code units
[...s].length;                    // codepoints
[...new Intl.Segmenter().segment(s)].length; // grapheme clusters (correct for display)

// UTF-8 byte length for DB storage checks:
new TextEncoder().encode(s).length;
```
Safe max-length validation:
```ts
function isWithinLimit(value: string, maxGraphemes: number): boolean {
  return [...new Intl.Segmenter().segment(value)].length <= maxGraphemes;
}
```
DB column sizing:
- MySQL utf8mb4 `VARCHAR(255)` = 255 characters
- PostgreSQL `character varying(n)` = n codepoints
- SQLite has no enforcement; validate at application layer

## Gotchas
- `s.codePointAt()` returns the full codepoint; `s.charCodeAt()` returns the surrogate value
- `Array.from(s)` iterates codepoints, not graphemes
- Twitter character limit is in grapheme clusters

## Related
- `grapheme-cluster-iteration.md`
- `emoji-unicode-handling.md`
