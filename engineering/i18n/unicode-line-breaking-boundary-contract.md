# Unicode line-breaking boundary contract

**Issue:** A layout engine inserts line breaks by whitespace alone, or applies emergency wrapping everywhere, damaging scripts, emoji sequences, URLs, and copy/paste fidelity.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Unicode Standard Annex #14 defines line-break opportunities from character classes and rules. Use a conformant platform engine, then layer product policy for hyphenation and emergency overflow; do not invent a regex segmenter.

**Source:** [Unicode Standard Annex #14: Unicode Line Breaking Algorithm](https://unicode.org/reports/tr14/)

## Controls

- preserve grapheme clusters and shaping-sensitive sequences;
- set the correct language metadata so browser tailoring and dictionary segmentation can engage;
- distinguish normal opportunities, discretionary hyphenation, and last-resort `overflow-wrap`;
- isolate untrusted long tokens without globally enabling arbitrary breaks;
- pin or record Unicode/ICU versions where server-rendered wrapping affects durable output.

## Verification

- fixtures include CJK, Thai, combining marks, emoji ZWJ sequences, non-breaking spaces, URLs, and mixed-direction text;
- resize tests ensure no clipping while ordinary words remain intact;
- copied text does not acquire visual-only break characters;
- PDF/server rendering is compared with the browser for critical documents.

## Gotchas

- UAX #14 permits tailoring; identical Unicode versions do not guarantee identical fonts or shaping.
- line breaking is not grapheme segmentation or word segmentation.
- `word-break: break-all` is an emergency tool, not an internationalization strategy.
