# CLDR metazone name fallback

**Issue:** A product displays raw IANA zone IDs or one fixed abbreviation for all dates, producing ambiguous or historically wrong localized time-zone names.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

CLDR metazones group zones for localized generic/standard/daylight naming over defined time ranges. Use an instant, locale, and IANA zone with a CLDR/Intl formatter; do not persist a metazone as the user's time zone.

**Source:** [Unicode LDML Dates — time-zone names and metazones](https://unicode.org/reports/tr35/tr35-dates.html#Time_Zone_Names)

## Controls

- store the IANA zone and instant;
- pin CLDR/TZDB versions for reproducible documents;
- request a documented name style and tolerate fallback;
- show offsets/city context where abbreviations are ambiguous;
- refresh future schedules when TZDB rules change.

## Verification

Test winter/summer, historical changes, zones sharing a metazone, non-hour offsets, missing localized names, locale fallback, and server/client version differences.

## Gotchas

Metazones are presentation data, not scheduling identifiers. Abbreviations are not globally unique. A name can change with date even when the IANA zone does not.
