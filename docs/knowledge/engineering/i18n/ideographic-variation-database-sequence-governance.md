# Ideographic Variation Database sequence governance

**Issue:** A system drops variation selectors from registered ideographic sequences, changing a requested glyph form in names, publishing, or archival content.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

UTS #37 defines the Ideographic Variation Database (IVD). Preserve a registered base ideograph plus variation selector as a sequence and ensure the selected font supports the intended collection.

**Source:** [Unicode Technical Standard #37: Ideographic Variation Database](https://unicode.org/reports/tr37/)

## Controls

- retain variation selectors through storage, normalization, search, and transport;
- record the IVD collection/version used by authoritative content;
- use fonts whose cmap format 14 data supports required sequences;
- define a visible fallback/review process for unsupported sequences;
- distinguish glyph variation from character identity decisions.

## Verification

Test supported/unsupported registered sequences, copy/paste, normalization, database round-trip, PDF export, font fallback, and search. Byte/code-point fixtures must detect selector loss.

## Gotchas

An unsupported selector may render as the base glyph with no obvious error. IVD registration does not bundle fonts. Do not invent private sequences when interoperable exchange matters.
