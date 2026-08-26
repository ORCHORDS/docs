# Locale week start, weekend, and week-numbering semantics

**Issue:** A calendar or reporting UI assumes Monday/Sunday starts, Saturday/Sunday weekends, or ISO week numbering for every locale.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

Locale week conventions include first day, weekend days, and the minimum number of days required in the first week. They are presentation and reporting rules; do not derive them from a user’s IP address or hard-code a regional default.

**Source:** [Intl.Locale.getWeekInfo() — MDN](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Locale/getWeekInfo)

## Pattern

Use an explicit user/account locale, retrieve locale week data when supported, and use maintained CLDR/Intl-backed fallback data where it is not. Keep stored business dates and week identifiers unambiguous.

```js
const locale = new Intl.Locale("en-GB");
const { firstDay, weekend, minimalDays } = locale.getWeekInfo();
```

## Verification

- calendar grids, weekend styling, and weekly reports match selected locales;
- boundary dates around January 1 reflect the selected week-number rule;
- a locale without native support follows a tested fallback;
- user-selected locale changes update presentation without changing stored instants;
- accessibility labels name the actual localized day/week context.

## Gotchas

- `getWeekInfo()` is not Baseline across all widely used browsers; provide a fallback.
- ISO week numbers and locale week numbers are not interchangeable.
- Weekend days are not universally Saturday/Sunday.
- Locale preferences are not proof of timezone, legal region, or work schedule.

## Related

- `i18n/date-time-timezone.md`
- `i18n/locale-preferences.md`
- `testing/timezone-dst-boundary-regression-tests.md`
