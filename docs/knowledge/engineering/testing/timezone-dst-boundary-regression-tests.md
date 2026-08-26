# timezone-dst-boundary-regression-tests

**Issue:** Tests freeze a local clock or a single offset and miss skipped/repeated local times, offset changes, and date-versus-instant serialization defects.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

A local date/time, a UTC instant, and a time-zone-aware date/time are different data types. Daylight-saving transitions create local times that are skipped or repeated, so tests that use only ordinary dates can pass while production schedules, expiry windows, or reports are wrong.

**Source:** [TC39 Temporal documentation](https://tc39.es/proposal-temporal/docs/).

## Fix

- represent a date-only value, local date/time, instant, and zoned date/time separately;
- test at least one non-DST zone and both a skipped and repeated local-time boundary in relevant IANA zones;
- freeze an instant in tests, then derive local display/schedule values from it;
- test parse, serialize, storage, API, and UI round trips;
- make ambiguity resolution explicit for repeated local times and invalid-time handling explicit for skipped times;
- include leap-day and cross-year boundaries where business rules use calendar dates.

## Verification

- A scheduled action behaves correctly across spring-forward and fall-back boundaries.
- The same instant renders consistently for intended zones.
- A date-only value does not shift a day after serialization.
- Ambiguous local input follows the documented policy.

## Related

- `i18n/date-formatting-intl.md`
- `testing/time-dependent-code.md`
