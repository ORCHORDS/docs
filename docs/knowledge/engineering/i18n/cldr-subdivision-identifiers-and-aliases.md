# CLDR subdivision identifiers and aliases

**Issue:** Country subdivisions change names, codes, and parent territories. Storing display labels or assuming every code is a current ISO subdivision breaks address validation, taxation, shipping, and historical records.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation
Store a canonical territory plus subdivision identifier and the data-version used; localize labels at display time from CLDR. Apply CLDR aliases as explicit migrations, preserving the submitted value and migration reason. Do not infer legal, postal, or tax validity solely from locale data; use the governing authority's current dataset for those decisions.

## Verification
Test deprecated aliases, one-to-many replacements, unknown/private values, parent mismatch, historical records, locale fallback, CLDR upgrades, and round-trip imports. Never silently choose among ambiguous replacements.

## Gotchas
CLDR localization and containment data are not a postal-address certification service. Subdivision codes can be reused or reorganized.

## Sources
- Unicode Consortium, [UTS #35 Locale Data Markup Language](https://unicode.org/reports/tr35/)
- Unicode CLDR, [Subdivision validity data](https://github.com/unicode-org/cldr/blob/main/common/validity/subdivision.xml)
