# Intl.Locale Week Information and Calendar Boundaries

**Issue:** Hard-coding Monday/Sunday starts, Saturday-Sunday weekends, or ISO first-week rules produces incorrect calendars, scheduling, and week-number labels for many locales.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Construct an `Intl.Locale` from the resolved user locale and call `getWeekInfo()` when supported. Use:

- `firstDay` to order calendar columns;
- `weekend` to style locale weekend days without assuming they are Saturday/Sunday;
- `minimalDays` when computing the first numbered week.

The returned weekday integers use Monday=1 through Sunday=7; do not pass them directly to JavaScript `Date.getDay()`, which uses Sunday=0. Keep display convention separate from business calendars, holiday data, work schedules, and user overrides.

Feature-detect because some engines exposed an earlier `weekInfo` accessor and current support is not universal. Use CLDR-derived server/polyfill data pinned to a version for fallback, and document update cadence.

## Verification

Test locales with Sunday and Monday week starts, non-Saturday/Sunday weekends, ISO four-day first-week rules, Unicode calendar/region overrides, RTL rendering, and year boundaries. Compare client and server calculations from the same locale-data version. Test invalid tags and missing API support.

## Gotchas

Locale is a formatting preference, not necessarily physical location or employer policy. Week number calculation also needs a calendar/date algorithm; `getWeekInfo()` supplies rules, not a week number. Locale data updates can legitimately change snapshots.

## Sources

- [MDN Intl.Locale.getWeekInfo](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Locale/getWeekInfo)
- [ECMA-402 Locale week info](https://tc39.es/ecma402/#sec-Intl.Locale.prototype.getWeekInfo)
- [Unicode TR35 week elements](https://unicode.org/reports/tr35/tr35-dates.html#Week_Data)
