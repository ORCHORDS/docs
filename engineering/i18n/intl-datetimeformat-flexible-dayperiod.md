# Intl.DateTimeFormat flexible day periods

**Issue:** A localized interface assumes every locale divides the day only into AM and PM, producing unnatural labels such as “12 at night” or unstable parsing contracts.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

ECMA-402 supports the `dayPeriod` option for localized flexible labels such as “in the morning” or “at night.” Treat these strings as presentation data; they are not machine-readable time ranges and must never drive scheduling logic.

**Sources:** [ECMA-402 Intl.DateTimeFormat](https://tc39.es/ecma402/#datetimeformat-objects) · [Unicode date-field symbols](https://unicode.org/reports/tr35/tr35-dates.html#Date_Field_Symbol_Table)

## Controls

- construct the formatter with an explicit locale and time zone;
- choose `dayPeriod: "narrow" | "short" | "long"` only when the product needs flexible prose;
- keep the underlying instant or local-time model as structured data;
- use `formatToParts()` when markup must isolate the day-period token;
- feature-detect and define a reviewed fallback because support and locale data vary.

## Verification

- test boundary times around midnight, noon, morning, afternoon, evening, and daylight-saving transitions;
- assert behavior in multiple locales without matching exact English words;
- compare server and client output under pinned locale/time-zone inputs;
- confirm assistive text includes the complete, unambiguous time.

## Gotchas

- flexible periods are locale-defined and may overlap or have unequal lengths.
- formatted labels are unsuitable for parsing.
- omitting `timeZone` makes output depend on the host environment.
