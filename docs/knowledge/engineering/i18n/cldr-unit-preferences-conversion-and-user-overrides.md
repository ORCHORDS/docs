# CLDR unit preferences, conversion, and user overrides

**Issue:** Choosing metric versus US units alone is insufficient: preferred units depend on locale, measurement usage, thresholds, and explicit user overrides. Hard-coded conversions can produce unfamiliar or lossy output.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Store measurements in a canonical unit with declared precision. Resolve presentation units through CLDR unit-preference and conversion data using the locale, semantic usage, and supported Unicode locale overrides.

## Controls

- Distinguish measurement system (`ms`), unit override (`mu`), region override (`rg`), and base locale.
- Pass a semantic usage such as person height; do not select by physical quantity alone.
- Use CLDR conversion constants and threshold rules from one pinned release.
- Preserve the original entered unit and value when audit or user editing requires it.
- Apply explicit, validated user preference ahead of inferred regional defaults.
- Define rounding after conversion and before localized formatting.
- Reject incompatible dimensions; never convert by matching display labels.
- Keep calculations in canonical units and localize only at presentation boundaries.

## Verification

Run CLDR unit conversion, preference, and locale-preference test data. Cover compound outputs, threshold boundaries, negative values, high precision, `ms`/`mu`/`rg` interactions, and locale fallback. Confirm round-trip tolerances are appropriate for the domain.

## Gotchas

A locale’s preferred unit can vary by usage. Unit formatting does not perform policy decisions about safe medical, financial, or engineering precision. CLDR data changes between releases, so output drift must be reviewed.

## Sources

- [Unicode LDML Unit Preference and Conversion Data](https://unicode.org/reports/tr35/tr35-general.html#Unit_Preference_and_Conversion_Data)
- [Unicode LDML supplemental unit tests](https://www.unicode.org/reports/tr35/tr35-info.html#Unit_Preferences)
