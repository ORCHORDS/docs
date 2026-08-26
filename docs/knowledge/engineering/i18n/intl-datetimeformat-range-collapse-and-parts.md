# Intl.DateTimeFormat Range Collapse and Parts

**Issue:** Applications concatenate two independently formatted dates, producing repeated fields, wrong locale punctuation, ambiguous time zones, and strings that cannot be styled without unsafe parsing.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use one `Intl.DateTimeFormat` instance and call `formatRange(start, end)` so the locale can collapse shared fields. Use `formatRangeToParts()` when the UI needs semantic styling; branch on each part's `source` (`startRange`, `endRange`, or `shared`) and `type`, never on punctuation text.

Require both inputs to represent compatible date/time values, choose the time zone explicitly, and validate `start <= end` before formatting. Feature-detect range methods and fall back to two complete `format()` results joined with a localized message template.

## Verification

Test same-day, cross-day, cross-month, cross-year, daylight-saving overlap/gap, different calendars, numbering systems, right-to-left locales, and equal endpoints. Snapshot semantic parts rather than one engine's exact whitespace. Confirm the selected time zone is visible when omission would make a range ambiguous.

## Gotchas

Range formatting is presentation, not interval arithmetic. It does not convert a date-only business interval into instants or decide inclusive endpoints. Literal separators may contain directional or nonbreaking characters. Do not split the rendered string to reconstruct dates.

## Sources

- [ECMA-402 current Internationalization API specification](https://tc39.es/ecma402/)
- [Unicode Locale Data Markup Language, dates](https://unicode.org/reports/tr35/tr35-dates.html)
