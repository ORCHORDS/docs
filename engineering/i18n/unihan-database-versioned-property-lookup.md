# Unihan database versioned property lookup

**Issue:** A product treats Han characters as carrying one universal pronunciation, radical, or regional form and bakes an unversioned mapping into search or annotation.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

UAX #38 defines the Unihan Database and its property model. Treat properties as versioned scholarly/interoperability data, not as a complete dictionary or a user-language decision.

**Source:** [Unicode Standard Annex #38: Unicode Han Database](https://unicode.org/reports/tr38/)

## Controls

- pin the Unicode/Unihan release and record provenance;
- select only documented properties needed by the feature;
- preserve multiple readings/variants instead of choosing the first;
- keep locale and user preference separate from code-point metadata;
- regenerate indexes deterministically during upgrades.

## Verification

Test unified ideographs, compatibility ideographs, extension blocks, multiple readings, missing properties, and version upgrades. Confirm fallback never fabricates pronunciation or semantic equivalence.

## Gotchas

Unicode unification does not mean glyphs or readings are identical across languages. Unihan is not normative language pedagogy. Fonts and locale determine rendered glyph forms separately.
