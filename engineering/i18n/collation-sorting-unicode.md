# collation-sorting-unicode

**Issue:** Sorting strings correctly across locales using the Unicode Collation Algorithm
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
JavaScript default `Array.sort()` uses code-point order, which mis-sorts accented characters and fails for CJK and Thai.

## Pattern / Solution
```js
const words = ['eclair', 'apple', 'Banana', 'angstrom'];

// Wrong: code-point sort
words.sort();

// Correct: locale-aware
words.sort((a, b) => a.localeCompare(b, 'en', { sensitivity: 'base' }));

// High-perf: reuse Collator
const coll = new Intl.Collator('de', { sensitivity: 'variant', caseFirst: 'upper' });
words.sort(coll.compare);

// Natural sort (file2 before file10)
const natColl = new Intl.Collator('en', { numeric: true });
['file10', 'file2', 'file1'].sort(natColl.compare);
// -> ['file1', 'file2', 'file10']
```

## Gotchas
- `sensitivity: 'base'` ignores case and accents; `'variant'` distinguishes everything
- Swedish treats a-umlaut, o-umlaut as separate letters after z
- `Intl.Collator` is ~10x faster than repeated `localeCompare` for large arrays

## Related
- `unicode-normalization-nfc-nfd.md`
- `unicode-collation-2026.md`
