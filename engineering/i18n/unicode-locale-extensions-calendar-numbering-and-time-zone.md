# Unicode locale extensions: calendar, numbering system, and time zone

**Issue:** Treating a locale as only a language-region pair loses user-selected calendar, numerals, collation, and time-zone preferences. Ad-hoc locale strings also fragment cache keys and can produce inconsistent server/client formatting.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Core rule

Use canonical BCP 47 language tags and the Unicode `u` extension where an explicit locale preference is part of the product contract. Relevant keys include `ca` (calendar), `nu` (numbering system), `co` (collation), `hc` (hour cycle), and `tz` (time zone). Support depends on the platform and formatter, so feature-test the formatter behavior rather than assuming every key changes output.

## Implementation guidance

- Store a canonical locale identifier separately from the user's instant/time-zone data; a locale time-zone preference is not a substitute for recording event instants in UTC.
- Prefer platform internationalization APIs that accept locales and explicit options. Do not manually swap digits, month names, or date order.
- Canonicalize and validate accepted tags at input boundaries; reject or map unsupported product choices rather than inventing private conventions.
- Make calendar and numeral selection explicit in reports, invoices, and exports where a change can alter interpretation.
- Build cache keys from canonical locale/options actually used to format output, while avoiding unbounded user-provided tag variation.
- Test representative combinations: language-region fallback, non-Latin digits, alternate calendar, hour-cycle preference, and a locale whose collation differs from code-point order.

## Failure modes

- Assuming `en-US` semantics for every English-speaking user.
- Conflating an IANA time-zone identifier with a locale's Unicode `tz` key.
- Serializing formatted display strings as business data; retain machine-readable values alongside presentation.
- Advertising a locale option that the runtime cannot honor consistently on all supported clients.

## Sources

- [Unicode Technical Standard #35 — Unicode Locale Data Markup Language](https://www.unicode.org/reports/tr35/tr35.html)
- [IETF BCP 47 language tags (RFC 5646)](https://datatracker.ietf.org/doc/html/rfc5646)

## Tags

`i18n` `bcp47` `cldr` `calendar` `numbering-system`
