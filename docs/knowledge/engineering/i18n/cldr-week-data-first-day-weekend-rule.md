# CLDR Week Data: First Day and Weekend Rules

CLDR week data encodes, per territory, which day starts the week and which days constitute the weekend. Calendar widgets, date-range pickers, weekly aggregation reports, and scheduling systems all depend on it, yet many teams hardcode a Sunday-start week with a Saturday-Sunday weekend and ship subtle defects for users in the Middle East, parts of Latin America, and locales with mixed conventions. This article covers the structure of `weekData`, how to consume it correctly, and how to validate week-boundary behavior against pinned CLDR data.

## Scope

This article addresses the `weekData` element of CLDR supplemental data (UTS #35 Part 1), specifically `firstDay`, `weekendStart`, `weekendEnd`, and `minDays`. It covers per-territory variation, defaults, and the engineering consequences for calendar rendering and weekly bucketing. It does not cover ISO 8601 week numbering (`week of year` rules), calendar systems other than Gregorian, or week-of-month computations except where they intersect first-day rules.

## Workflow or implementation guidance

The `weekData` element records three families of facts. `firstDay` maps territories to the day that begins the week: most of the world uses Monday, the United States and China default to Sunday, and much of the Arab world uses Saturday. `weekendStart` and `weekendEnd` bracket the weekend: a single element with `day="sat"` and `day="sun"` covers the common case, while territories like Israel encode Friday-Saturday and Iran encodes Thursday-Friday (recorded via weekend start/end pairs). `minDays` records the minimum number of days a week must have in the first week of the year for week-numbering purposes, and varies between 1 and 4.

A correct consumption workflow:

1. Extract `weekData` from the pinned CLDR release's `supplementalData.xml`. Note the element stores defaults at the world level (`001`) and territory-specific overrides; resolution order is territory, then parent territory via containment, then world default.
2. Represent days canonically as `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun` tokens per the LDML day identifier vocabulary, converting to integer offsets only at the rendering boundary and only after fixing an origin day for the calendar grid.
3. Compute the calendar grid origin: for a Monday-start territory the leftmost column is Monday; for a Sunday-start territory it is Sunday. The column index of any civil date is `(daysSince(originDate) mod 7)` where `originDate` is a date whose weekday matches the configured first day.
4. For weekly aggregation, define week buckets by half-open intervals `[weekStart, weekStart+7d)` where `weekStart` is the date of the configured first day on or before the event date. Never bucket by `floor(eventDate / 7)` arithmetic, which ignores first-day variation entirely.
5. For weekend detection, treat the weekend as an inclusive range from `weekendStart` to `weekendEnd` with wraparound: a Friday-Saturday weekend means Friday, Saturday, and, if the interval is recorded as fri-to-sat, no other days. Render non-working-day styling from this set rather than from a hardcoded Saturday-Sunday pair.

A concrete trap: weekly metrics dashboards often group events by ISO week (Monday origin) while the user-facing calendar renders Sunday-start. Users in the United States see a week of March 1–7 in the picker but a metric labeled with the ISO week containing March 3, whose Monday-origin bucket spans a different set of events. The correction is to derive both the picker and the bucketing from the same resolved `weekData` for the user's territory, and to label buckets with the week start date rather than a week number to avoid ambiguity.

Territory inheritance deserves care. CLDR resolves `firstDay` for `en-CA` to Sunday (inherited), while `en-GB` resolves to Monday; a global application that keys week configuration on language instead of territory will misconfigure Canada. Always resolve through territory, falling back to the world default (`001`), which is Monday for `firstDay`.

## Controls

- Pin the CLDR or ICU version so week data is reproducible; document the pin in the build configuration next to other locale data pins.
- Unit-test week-boundary logic against a table of territories with divergent rules: `US` (sun start, sat–sun weekend), `SA` (sun start per CLDR with fri–sat weekend), `IR` (sat start, thu–fri weekend), `IL` (sun start, fri–sat weekend), `GB` (mon start, sat–sun weekend).
- Assert at startup that every rendered calendar consumes a resolved `weekData` value rather than a constant; a code-level lint can flag literal weekday names in rendering code.
- Label weekly report buckets with the inclusive week start date in ISO 8601 format (`2026-W09` alternatives confuse; `2026-02-23` is unambiguous), and record the territory whose week rules produced the bucket.
- When territory data is missing (unregistered region codes), resolve through containment ancestors before falling to `001`, and log the fallback chain.

## Validation evidence

- The `weekData` element, its `firstDay`, `weekendStart`, `weekendEnd`, and `minDays` attributes, and territory-default resolution are specified in UTS #35 Part 1, published by the Unicode Consortium.
- The CLDR project publishes the current supplemental data including week data at cldr.unicode.org, where release notes record territory-level week-rule corrections.
- Cross-checking a pinned release shows `IR` carries `thu–fri` weekend and Saturday first day while `AF` carries Friday-Saturday weekend with Saturday first day — confirming the data is territory-keyed and materially different from a US default.

## Failure modes and correction

- **Hardcoded Sunday start.** Symptom: Middle Eastern users see working days split across grid rows, and weekly totals disagree with local expectations. Correct by resolving `firstDay` from `weekData` per territory.
- **Weekend assumed Saturday-Sunday.** Symptom: Friday morning deployments alert on-call staff in Israel during their weekend. Correct by consulting `weekendStart`/`weekendEnd` for the on-call territory.
- **Language-keyed configuration.** Symptom: `en-CA` users get Monday-start grids. Correct by keying on territory and inheriting through containment.
- **Arithmetic week bucketing.** Symptom: dashboards show partial weeks at month boundaries regardless of territory. Correct by computing week buckets from the resolved first day with half-open intervals.
- **Weekend range without wraparound handling.** Symptom: territories whose weekend spans the grid edge (Saturday start with Sunday last column) misclassify edge days. Correct by comparing canonical day order cyclically rather than with plain integer less-than on a Sunday-origin scale.

## Limitations

- `weekData` reflects territory-level convention, not individual organizations; companies with global weekend policies must layer their own override table on top.
- The data encodes conventional weekends, not public holidays; holiday calendars are a separate dataset.
- `minDays` interacts with week-numbering schemes (including ISO 8601) in ways CLDR does not fully prescribe for all territories; week-number display requires an explicit scheme choice.
- Weekend definitions are slow-moving but real changes do occur (for example, historic shifts in several territories); the data remains a snapshot of the pinned release.

## Canonical sources

- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML), Part 1: Localized Common Data — week data: https://unicode.org/reports/tr35/
- Unicode Consortium, CLDR — Common Locale Data Repository: https://cldr.unicode.org/
