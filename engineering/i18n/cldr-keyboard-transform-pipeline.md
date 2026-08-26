# CLDR keyboard transform pipeline

**Issue:** Software keyboards and transliteration input need ordered transforms, modifier mappings, repertoire metadata, and locale fallback. Treating CLDR keyboard data as a simple character map breaks dead keys, sequences, hardware layouts, and script-specific input.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Parse a pinned CLDR keyboard-data version with schema validation. Keep physical key mapping, modifier combinations, transforms, display labels, and locale fallback as separate stages. Apply transforms incrementally with bounded context and deterministic longest-match rules; prevent recursive or unbounded rewrites. Preserve raw input and let users switch layouts without corrupting composed text.

## Verification

Test dead keys, multi-code-point sequences, combining marks, supplementary characters, modifier fallbacks, hardware variations, deletion through composition, locale fallback, invalid data, and upgrades. Compare conformance fixtures for every supported layout.

## Gotchas

Keyboard locale does not necessarily equal UI locale. Unicode normalization must be an explicit boundary; premature normalization can change transform matching.

## Sources

- Unicode Consortium, [UTS #35 — Keyboard Data](https://unicode.org/reports/tr35/tr35-keyboards.html)
- Unicode Consortium, [CLDR keyboards repository](https://github.com/unicode-org/cldr/tree/main/keyboards)
