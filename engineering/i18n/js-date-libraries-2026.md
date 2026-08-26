# js-date-libraries-2026

**Issue:** A team starts a new JavaScript project and needs a date library. The team reads "Moment.js is dead, don't use it." The team has 4-5 viable options: date-fns, Day.js, Luxon, Temporal API. The team needs a 2026 decision framework.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

JavaScript date handling was broken for 30 years (the native `Date` object is mutable, has DST bugs, no time zone clarity, no calendar systems). In 2026, the Temporal API is shipping natively (Chrome 144 January 2026, Firefox 139 May 2025) but not yet universal. Production needs a library today.

## Root cause

Four viable 2026 options: date-fns v4 (24M weekly downloads, tree-shakeable, ~2-13KB, TypeScript-first, now with @date-fns/tz for time zones), Day.js (15M weekly, 2KB gzipped, Moment-compatible chaining), Luxon (4M weekly, 24KB, IANA zones native), Temporal API (native, ~20KB polyfill). Each has trade-offs.

## The 4 libraries compared

| Library | Weekly DL | Bundle | Time zone | Calendar | API style | Status |
|---|---|---|---|---|---|---|
| date-fns v4 | 24M | 2-13KB | @date-fns/tz | Gregorian only | Functional | Active |
| Day.js | 15M | 2KB + plugins | Plugin | Gregorian only | Chained (Moment-like) | Active |
| Luxon | 4M | 24KB | Native (Intl) | Gregorian only | OOP (Immutable) | Active |
| Temporal | (native) | 20KB polyfill | Native | 15+ calendars | OOP (Immutable) | Stage 3 / Chrome 144+, Firefox 139+ |
| Moment.js | 23M (legacy) | 70KB | Plugin | Gregorian only | Chained (mutable) | Maintenance-only |

## The 5 decision rules

1. **New TypeScript project, Node.js or browser** → date-fns v4. Best TypeScript inference, tree-shaking, ~5KB for typical usage.
2. **Migrating from Moment.js** → Day.js. API compatible, ~2KB, low migration cost.
3. **Timezone-heavy international app, scheduling, logistics** → Luxon. Best-in-class IANA handling via Intl, immutable.
4. **Greenfield, long horizon, calendar systems beyond Gregorian** → Temporal with @js-temporal/polyfill now, native when available.
5. **Avoid Moment.js for new projects.** Deprecated, 70KB, mutable, in maintenance.

## The 5 anti-patterns

1. **Using Moment.js in 2026.** 70KB, mutable, maintenance-only. Migration tools exist (moment-to-date-fns).
2. **Building timezone logic on native Date.** DST bugs, no zone clarity, no calendar systems. The original 30-year-old problem.
3. **Mixing date libraries in the same app.** Pick one; date-fns and Day.js objects don't interoperate cleanly.
4. **Skipping the polyfill on Temporal and assuming native.** As of mid-2026, Safari stable doesn't have Temporal. Use the @js-temporal/polyfill.
5. **Computing time zones from UTC offsets.** Always use IANA names (Europe/Warsaw), not +01:00. DST rules are zone-specific.

## The 5-step adoption pattern

1. Detect Temporal availability: `if (typeof Temporal !== 'undefined')` use native, else polyfill, else fallback library.
2. Pick fallback library based on team context (above 5 rules).
3. Centralize date logic in `utils/format.js` or similar. Don't sprinkle `Intl.DateTimeFormat` calls everywhere.
4. Store UTC in the database, convert to user zone only at display.
5. Build a test matrix: a European locale with space separator, an Eastern Arabic numeral locale, a calendar system test for Temporal users.

## Verification

The tell that date handling is right:

- Bundle impact matches decision (date-fns tree-shaken to ~5KB, Day.js core 2KB, etc.)
- Time zones use IANA names, not UTC offsets
- All `Date` objects are UTC in the data layer
- Display layer converts to user zone
- DST transitions tested (US spring forward, EU fall back, southern hemisphere)
- One date library across the app, not mixed

The tell it isn't:

- "We use Moment because it's familiar"
- "+09:00 stored in the database"
- Multiple date libraries loaded
- `new Date(some_string)` without explicit zone

## Gotchas

- **Temporal polyfill is 20KB.** Acceptable for new projects; significant for legacy bundles.
- **Day.js timezone plugin uses Intl.DateTimeFormat.** Fails in Node.js builds with reduced ICU data. Set `--with-intl=full-icu` or use `full-icu` package.
- **date-fns v4 changed imports.** `date-fns/format` is replaced with named imports `import { format } from 'date-fns'`.
- **Luxon depends on Intl.** Same Node.js reduced-ICU risk.
- **Temporal calendar support is the killer feature.** Japanese era, Hebrew, Chinese, Buddhist, etc. All major JS date libraries are Gregorian-only.

## Related

- `i18n/timezone-iana-temporal-2026.md` - timezone and Temporal API details
- `i18n/number-currency-formatting-2026.md` - Intl.NumberFormat
- `i18n/character-encoding-utf-8-2026.md` - UTF-8 and Unicode normalization

## Source URLs (verified 2026-08-10)

- https://www.pkgpulse.com/guides/best-javascript-date-libraries-2026
- https://www.pkgpulse.com/guides/date-fns-v4-vs-temporal-api-vs-dayjs-date-handling-2026
- https://worldtick.click/en/articles/javascript-datetime-libraries/
- https://tc39.es/proposal-temporal/docs/
- https://momentjs.com/docs/
