# Intl.DisplayNames for stable codes, labels, and fallbacks

**Issue:** Applications often persist translated labels or maintain incomplete hand-written maps for languages, regions, scripts, currencies, calendars, and date-time fields.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Persist canonical domain codes, never localized display strings. Produce UI labels at render time with `Intl.DisplayNames`.
- Specify `type`, `style`, `fallback`, and for language names `languageDisplay`; do not rely on implicit product-wide defaults.
- Canonicalize and validate user/configuration input before calling `.of()`. Different types accept different code grammars.
- Use `fallback: "none"` when an untranslated code should trigger the product's explicit fallback or telemetry rather than leak a raw code into UI.
- Cache formatters by resolved locale and option tuple, but invalidate them when the active locale or bundled runtime changes.

## Verification

1. Test language, region, script, currency, calendar, and date-time-field labels in representative locales.
2. Cover dialect versus standard language display and narrow/short/long styles.
3. Assert behavior for unsupported locales, structurally invalid codes, valid-but-unknown codes, and missing locale data.
4. Snapshot codes rather than localized wording; use semantic assertions for labels because runtime CLDR data changes.
5. Compare server and browser output if rendering is hydrated, and prevent a locale-data mismatch from causing DOM replacement.

## Gotchas

Locale data availability is implementation-defined within ECMA-402 constraints, so two runtime versions can produce different correct wording. `fallback: "code"` can expose opaque identifiers to users. Display names are labels, not identifiers and not appropriate for authorization or database joins. Currency display names do not perform money formatting.

## Sources

- [ECMA-402: DisplayNames Objects](https://tc39.es/ecma402/#displaynames-objects)
- [MDN: Intl.DisplayNames](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DisplayNames)
