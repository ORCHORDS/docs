# internationalisation-costs-triple-if-retrofitted

**Issue:** Internationalisation (i18n) added to an existing codebase costs three times more than building it in from the start
**Date:** 2026-08-11
**Status:** documented

## What happened
A SaaS product expanded into Japan and Germany two years after launch. The codebase had hardcoded English strings throughout, date and number formatting embedded in business logic, LTR-only CSS, and a single-timezone database design. Adding i18n support required touching 1,200 files, rewriting three core modules, and a six-month engineering effort before a single translated string could be displayed.

## The lesson
Even if you only ship in English today, build with i18n in mind from the start: use a translation key system for all user-visible strings, store timestamps in UTC, use locale-aware date/number formatting libraries, and avoid hardcoding text in CSS. The marginal cost of doing this correctly in greenfield development is roughly 10-15%; the cost of retrofitting is 3-5x the original development cost.

## Why it matters
International markets represent growth. Missing i18n infrastructure blocks you from capturing them quickly. By the time a business opportunity requires i18n, the retrofit cost delays the launch and may make it economically unviable.

## How to apply
- [ ] Use a translation system (i18next, gettext, ICU format) from day one, even for a single language.
- [ ] Externalize all user-visible strings to translation files — no hardcoded copy in components.
- [ ] Store all timestamps in UTC; convert to local time at display time.
- [ ] Use locale-aware formatting for numbers, currencies, and dates (Intl API in JS, locale packages in other languages).
- [ ] Design layouts to handle both LTR and RTL text and strings up to 3x longer than English.

## Related
- `accessibility-is-not-optional.md`
- `mobile-first-means-api-first.md`
