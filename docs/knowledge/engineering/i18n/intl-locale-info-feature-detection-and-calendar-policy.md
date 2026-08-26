# Intl.Locale Information Feature Detection and Calendar Policy

**Issue:** Week boundaries, weekend days, text direction, hour cycles, and available calendars vary by locale and runtime data. Hard-coded assumptions break regional calendars, while proposal-era method names and partial engine support can fail at runtime.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Canonicalize and validate locale tags before constructing `Intl.Locale`; retain the user's explicit region or Unicode extension overrides where business rules allow them.
- Feature-detect each locale-information API rather than inferring support from browser or runtime version. Maintain a CLDR-backed server fallback for required scheduling logic.
- Use locale week information for presentation defaults, not immutable legal or billing rules. Store authoritative business-calendar rules separately and version them.
- Treat locale-derived text direction only as a fallback. Explicit content metadata and the actual script of user-supplied text take precedence.
- Do not assume weekends are Saturday and Sunday or even contiguous. Consume the returned list.
- When enumerating calendars, numbering systems, hour cycles, or time zones, distinguish “supported/preferred for a locale” from “the user's chosen setting.”
- Record the runtime and locale-data version in reproducibility tests because implementation-dependent lists can change.

## Verification

1. Test locales with different first weekdays, weekend definitions, directions, hour cycles, and regions.
2. Test a language-only tag, an explicit region, and Unicode extension overrides.
3. Run with every individual method absent to verify the fallback is granular.
4. Compare client display decisions to server scheduling rules around week and year boundaries.

## Gotchas

- The TC39 locale-info proposal can evolve; API names and availability require current feature detection.
- Locale defaults are preferences, not proof of a person's location or legal calendar.
- Direction metadata attached to content is stronger than a locale-derived guess.

## Sources

- [TC39 Intl Locale Info proposal](https://tc39.es/proposal-intl-locale-info/)
- [Unicode LDML](https://www.unicode.org/reports/tr35/)
