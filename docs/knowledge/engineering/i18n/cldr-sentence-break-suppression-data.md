# CLDR sentence-break suppression data

**Issue:** Generic Unicode sentence boundaries can split after abbreviations such as titles, producing broken previews, summaries, captions, or sentence navigation.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Apply Unicode segmentation rules with the resolved locale’s CLDR sentence-break suppression data. Keep segmentation separate from translation and never invent a universal abbreviation list.

## Controls

- Resolve locale fallback before loading suppressions.
- Distinguish standard and strict suppression behavior where data defines variants.
- Pin Unicode and CLDR versions together.
- Preserve original offsets using the indexing convention required by the caller.
- Run segmentation before truncation or sentence-level UI operations.
- Keep user text unchanged; boundaries are annotations.
- Avoid treating sentence boundaries as security or grammar validation.
- Cache compiled rules by version and resolved locale.

## Verification

Use CLDR segmentation test data plus locale fixtures for titles, initials, decimals, ellipses, quotations, emoji, mixed scripts, and unknown locales. Assert stable offsets and fallback behavior across upgrades, reviewing every changed fixture.

## Gotchas

Suppressions are exceptions layered over segmentation rules, not a complete natural-language parser. Abbreviations can be context-sensitive. Byte, code-unit, code-point, and grapheme offsets are not interchangeable.

## Sources

- [Unicode LDML Segmentation Suppressions](https://unicode.org/reports/tr35/tr35-general.html#Segmentation_Suppressions)
- [Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
