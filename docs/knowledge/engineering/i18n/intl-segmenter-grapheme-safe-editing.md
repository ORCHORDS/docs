# Intl.Segmenter for grapheme-safe editing and truncation

**Issue:** JavaScript string indices and naive slicing operate on UTF-16 code units, so they can split emoji sequences, combining marks, and user-perceived characters.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `Intl.Segmenter(locale, {granularity: "grapheme"})` for cursor stops, visible-character limits, masking, and truncation.
- Use word or sentence granularity only for locale-sensitive product behavior that accepts implementation tailoring; never equate whitespace splitting with universal word boundaries.
- Keep offsets explicitly labeled as UTF-16 indices because segment `index` and `containing(index)` use JavaScript string indexing.
- Define whether stored limits are bytes, code points, grapheme clusters, or business characters, and enforce the same unit server-side.
- Cache Segmenter instances per locale/granularity rather than rebuilding them inside hot loops.

## Verification

1. Test combining accents, regional-indicator flags, skin-tone modifiers, variation selectors, keycaps, and multi-person ZWJ emoji.
2. Test scripts without spaces and mixed-script text under multiple locales.
3. Round-trip every segment and assert concatenation equals the original string exactly.
4. For every legal cursor boundary, assert truncation never produces an isolated surrogate or partial grapheme cluster.
5. Cross-check browser and server runtime versions and treat boundary changes from Unicode-data upgrades as reviewed behavior changes.

## Gotchas

A grapheme cluster is not necessarily one code point or one glyph and can occupy many UTF-16 code units. Word-likeness is implementation-dependent. Segmentation does not normalize Unicode, prevent confusables, or determine display width. CSS ellipsis can still be preferable when the goal is purely visual clipping.

## Sources

- [ECMA-402: Segmenter Objects](https://tc39.es/ecma402/#segmenter-objects)
- [Unicode Standard Annex #29: Text Segmentation](https://www.unicode.org/reports/tr29/)
