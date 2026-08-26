# non-gregorian-calendars-eras-2026

**Issue:** A product hardcodes "2026" everywhere and then ships to users who live in other calendar systems: Japanese users expecting imperial-era years (令和8年), Thai users whose locale defaults to the Buddhist calendar (2569), Saudi users on Hijri (1448 AH), and Hebrew-calendar users in leap-month years (5786). Dates render wrong, sorting breaks, and month arithmetic produces nonsense. This article covers the non-Gregorian calendar systems supported by `Intl.DateTimeFormat` and ICU/CLDR — `japanese` with eras, the five `islamic*` variants, `hebrew`, `buddhist`, `chinese`, `ethiopic`, `persian` — and the 2026 rules for displaying, storing, and computing dates across them.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 calendar systems you will actually meet

1. **Japanese imperial (`japanese`).** Gregorian months and days, but years counted within eras named for each emperor. CLDR data includes the current era Reiwa (令和, from 2019-05-01); formatting August 2026 yields 令和8年. ICU updates are how new eras arrive — an OS from before 2019 prints 平成31 forever.
2. **Islamic / Hijri (`islamic`, `islamic-civil`, `islamic-umalqura`, `islamic-tbla`, `islamic-rgsa`).** Lunar calendar, ~354 days/year; August 2026 falls in 1448 AH. The variants disagree by a day or more because they use tabular formulas, astronomical calculation, or observation-based starting points (see Gotchas).
3. **Hebrew (`hebrew`).** Lunisolar with variable month lengths and a leap month (Adar I/Adar II roughly every 2-3 years, 7 times per 19-year cycle). August 2026 is Av 5786. Never hardcode month indices; the leap month shifts everything.
4. **Buddhist (`buddhist`).** Gregorian structure plus 543 years; it is the *default* calendar for `th-TH`, so Thai users see 2569 unless you override. This is the classic "why does the year say 2569" support ticket.
5. **Chinese, Ethiopic (`ethiopic`/`ethioaa`), Persian (`persian`).** Chinese is lunisolar with leap months tracked via CLDR cycle data; Ethiopic runs ~7-8 years behind Gregorian (2018 EC in 2026 Gregorian) with 13 months; Persian (Solar Hijri) starts its year at the March equinox (1405 SH in August 2026). All format fine via `Intl`; arithmetic does not.

## The 5 formatting rules

1. **Pass `calendar` explicitly.** `new Intl.DateTimeFormat('ja-JP-u-ca-japanese', { era: 'long', year: 'numeric' })` or the options-bag form `{ calendar: 'japanese' }`. Relying on user/OS defaults makes output nondeterministic across environments (TC39 ecma402 #891 exists precisely because of this).
2. **Turn on the `era` field for era-based calendars.** Without `{ era: 'long' | 'short' | 'narrow' }`, the Japanese calendar shows a bare year number that is meaningless without the era name.
3. **Offer a Gregorian toggle.** Japanese and Thai users routinely *want* Western years in data-heavy contexts (tables, invoices) even when the localized UI defaults elsewhere. Pair the calendar with a user preference, not just the locale.
4. **Let the formatter produce month names.** Hebrew Adar I/II and Chinese leap months have no stable index you can map by hand; only CLDR data knows the names for a given instant.
5. **Cache formatter instances per (locale, calendar, options).** Same rule as `Intl.NumberFormat`: construction walks CLDR data and is not free in hot paths.

## The 5 data-handling rules

1. **Store instants, format at display.** Persist UTC timestamps (or Temporal `Instant`/`ZonedDateTime` when it ships); the calendar is a *presentation* choice, not a storage choice. Never store "Reiwa 8" in the database.
2. **Do arithmetic in a calendar-aware library.** `Intl` formats but does not compute. For "add one Hijri month" or "end of Hebrew month", use `@internationalized/date` (React Aria's Calendar system), Luxon, or `temporal-polyfill` — all carry their own calendar implementations.
3. **Prefer `Temporal` for new code paths.** The Temporal proposal models calendars first-class: `Temporal.PlainDate.from('2026-08-15').withCalendar('islamic-umalqura')` gives you `.year`, `.month`, `.era` directly. Until it ships, the polyfill is the same API.
4. **Validate with the calendar in mind.** A user-entered birth date of 2512 (Buddhist) or 1440 (Hijri) is valid input in those systems; rejecting non-Gregorian years as "not a number we accept" is a data-loss bug.
5. **Test rendering per calendar system.** Snapshot golden outputs for `ja-JP-u-ca-japanese`, `th-TH` (default buddhist), `ar-SA-u-ca-islamic-umalqura`, `he-IL-u-ca-hebrew` on every date-formatting change.

## The 5 gotchas that bite teams

1. **The five `islamic*` variants disagree.** `islamic-umalqura` (Saudi civil, astronomical) can differ from `islamic-civil` (tabular) and from locally crescent-sighted dates by 1-2 days. Pick one variant deliberately, document it, and let users report date disputes — there is no universally authoritative Hijri algorithm (CLDR design doc says exactly this).
2. **Thai `th-TH` defaults to Buddhist.** `new Date().toLocaleDateString('th-TH')` prints 2569 without asking you. If your backend then parses it as a Gregorian year, records land 543 years in the future. Force `-u-ca-gregory` when you mean Gregorian.
3. **Node.js `small-icu` builds lack non-Gregorian data.** Official Node binaries ship full-icu since v13, but slim Alpine/some-distro builds fall back to English/Gregorian-only; `calendar: 'islamic-umalqura'` silently degrades to Gregorian. Verify with `Intl.supportedValuesOf`-style checks or build with `full-icu`.
4. **Era boundaries are data, not code.** The next Japanese era transition will break any hardcoded era list. Keep ICU/CLDR (and OS/webview) updated, and never translate era names yourself — they come from CLDR.
5. **Year sorting across calendars is meaningless.** Sorting formatted date strings ("令和8年" vs "2026" vs "5786") is gibberish. Always sort/compare on the underlying timestamp and format afterwards.

## Source URLs (verified 2026-08-15)

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- https://girliemac.com/blog/2019/04/02/javascript-i18n-reiwa-era/
- https://github.com/tc39/ecma402/issues/891
- https://stackoverflow.com/questions/70996839/discrepancy-in-javascript-intl-datetimeformat-outputs-for-the-islamic-hijri
- https://cldr.unicode.org/development/development-process/design-proposals/islamic-calendar-types
- https://react-aria.adobe.com/internationalized/date/Calendar.html
- https://medium.com/@ahmelq30/date-in-javascript-a-deep-dive-into-arabic-and-hijri-calendars-localization-c632e89b79a2

## Related

- `i18n/date-formatting-intl.md` — the Gregorian baseline this builds on
- `i18n/timezone-iana-temporal-2026.md` — Temporal's model that carries calendars
- `i18n/locale-week-start-weekend-and-week-numbering.md` — other locale-varying date conventions
