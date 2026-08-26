# indic-script-rendering

**Issue:** Correctly rendering Devanagari and other Indic scripts in web applications
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Indic scripts use conjunct consonants formed by combining base characters with halant (virama). Incorrect shaping engines show disconnected components.

## Pattern / Solution
```html
<html lang="hi">
<p lang="ta">தமிழ்</p>
<p lang="bn">বাংলা</p>
```
Font stacks:
```css
:lang(hi), :lang(mr) { font-family: 'Noto Sans Devanagari', 'Mangal', sans-serif; }
:lang(ta) { font-family: 'Noto Sans Tamil', 'Latha', sans-serif; }
:lang(bn) { font-family: 'Noto Sans Bengali', 'Vrinda', sans-serif; }
```
Do not disable OpenType features:
```css
/* NEVER override font-feature-settings for Indic scripts -- breaks conjuncts */
```

## Gotchas
- Rendering requires a shaping engine (HarfBuzz); canvas 2D does not shape automatically
- String `.length` is meaningless for conjunct sequences; use `Intl.Segmenter`
- Devanagari sorting requires locale-specific collation (`Intl.Collator('hi')`)

## Related
- `grapheme-cluster-iteration.md`
- `unicode-normalization-nfc-nfd.md`
