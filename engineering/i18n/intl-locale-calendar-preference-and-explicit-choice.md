# Intl.Locale Calendar Preference and Explicit Choice

**Issue:** Assuming Gregorian dates from a language or country hides legitimate calendar preferences and can mislabel years, eras, and month/day fields.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use `new Intl.Locale(resolvedLocale).getCalendars()` when supported to obtain commonly used calendars in descending preference. If the locale includes a Unicode `ca` extension, the result represents that explicit calendar. Feature-detect because earlier engines exposed a `calendars` accessor and support remains limited.

Use the list to offer sensible choices, not to silently convert stored business dates. Persist the user's explicit calendar preference separately from the timestamp/date value. Format with `Intl.DateTimeFormat` using that calendar and display era/year fields appropriate to it. Keep contractual, fiscal, and backend protocols on their defined calendar and label conversions.

## Verification

Test locales with multiple calendars, explicit `-u-ca-` extensions, unsupported calendar identifiers, era boundaries, leap months, date-only values, time zones, SSR/client consistency, and fallback data. Verify parsing/editing does not assume displayed numeric fields are Gregorian.

## Gotchas

A locale preference list is not the user's religion or legal calendar. Calendar conversion is not time-zone conversion. Locale data changes can reorder defaults, so explicit saved preferences should remain stable.

## Sources

- [MDN Intl.Locale.getCalendars](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Locale/getCalendars)
- [ECMA-402 Locale calendar info](https://tc39.es/ecma402/#sec-Intl.Locale.prototype.getCalendars)
- [Unicode calendar identifiers](https://unicode.org/reports/tr35/#UnicodeCalendarIdentifier)
