# unicode-normalization-nfc-nfd

**Issue:** Normalizing Unicode strings to avoid comparison failures from different encodings
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The letter `e` with acute accent can be NFC (precomposed U+00E9) or NFD (e + combining accent). They look identical but strict equality returns false.

## Pattern / Solution
```js
const nfc = '\u00E9';      // e-acute precomposed
const nfd = 'e\u0301';     // e + combining accent

nfc === nfd;                              // false
nfc.normalize('NFC') === nfd.normalize('NFC'); // true

// Forms:
// NFC  - Decompose then recompose (preferred for web interchange)
// NFD  - Decompose only
// NFKC - Compatibility decomposition + composition (ligatures, fullwidth to ASCII)
// NFKD - Compatibility decomposition only

const store = (s) => s.normalize('NFC');
const searchKey = (s) => s.normalize('NFKC').toLowerCase();
```
macOS HFS+ produces NFD; Linux/Windows produce NFC. Files from Mac cause lookup failures on Linux servers.

## Gotchas
- PostgreSQL stores strings as-is; normalize before INSERT and before comparison
- NFC is the recommended form for HTML, JSON, and interchange formats
- NFKC collapses distinctions (superscripts) that may be meaningful

## Related
- `unicode-collation-2026.md`
- `grapheme-cluster-iteration.md`
