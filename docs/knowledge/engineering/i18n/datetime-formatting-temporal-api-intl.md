# Date/Time Formatting — Temporal API and Intl.DateTimeFormat

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application formats dates incorrectly for international users —
US users see MM/DD/YYYY while European users expect DD/MM/YYYY, but
your code uses a single hardcoded format. Time zones are broken:
events created in Tokyo show the wrong time for users in London. Date
arithmetic is buggy — adding one month to January 31 produces
inconsistent results depending on which library you use. Your codebase
has three different date libraries (moment.js, date-fns, Day.js)
because the built-in `Date` object is too limited.

## Context

The Temporal API reached TC39 Stage 4 in March 2026 and is part of
the ES2026 specification, with native support in Chrome 144, Firefox
139, and Edge 144. Temporal replaces the legacy `Date` object with
immutable, time-zone-aware types that handle calendar arithmetic
correctly. Combined with `Intl.DateTimeFormat` (available in all modern
browsers and Node.js since v12), JavaScript now has built-in date
formatting that respects locale conventions — date order, separators,
month names, numbering systems, and calendar types — without external
libraries. For i18n applications, the standard approach in 2026 is:
store timestamps as `Temporal.Instant` (UTC), perform arithmetic with
`Temporal.ZonedDateTime`, and format for display with
`Intl.DateTimeFormat`.

## Temporal types

```
Temporal.Instant
  → Exact point in time (UTC nanoseconds)
  → Use for: timestamps, API responses, database storage
  → Similar to: Unix timestamp, Date.now()

Temporal.ZonedDateTime
  → Instant + time zone + calendar
  → Use for: displaying events in user's local time
  → The default "reach for" type (replaces Date)

Temporal.PlainDate
  → Date only (no time, no timezone)
  → Use for: birthdays, holidays, due dates

Temporal.PlainTime
  → Time only (no date, no timezone)
  → Use for: business hours, alarm times

Temporal.PlainDateTime
  → Date + time (no timezone)
  → Use for: calendar events before timezone assignment

Temporal.Duration
  → A length of time (hours, minutes, days)
  → Use for: countdowns, time differences, scheduling
```

## Temporal API usage

### Creating dates

```javascript
// Exact moment in time
const now = Temporal.Now.instant();
const fromString = Temporal.Instant.from("2026-08-16T14:30:00Z");

// Date + time in a specific timezone
const meeting = Temporal.ZonedDateTime.from({
  year: 2026, month: 8, day: 16,
  hour: 14, minute: 30,
  timeZone: "America/New_York",
});

// Date only (no timezone ambiguity)
const birthday = Temporal.PlainDate.from("1990-03-15");
const holiday = Temporal.PlainDate.from({ year: 2026, month: 12, day: 25 });
```

### Date arithmetic

```javascript
// Add 3 months and 5 days
const future = Temporal.PlainDate.from("2026-01-31")
  .add({ months: 3, days: 5 });
// Result: 2026-05-05 (handles month-end correctly)

// Duration between two dates
const start = Temporal.PlainDate.from("2026-01-01");
const end = Temporal.PlainDate.from("2026-08-16");
const diff = start.until(end, { largestUnit: "months" });
// Result: P7M15D (7 months, 15 days)

// Compare dates
const isAfter = end.since(start).sign === 1; // true
```

### Timezone conversions

```javascript
const meetingNY = Temporal.ZonedDateTime.from({
  year: 2026, month: 8, day: 16,
  hour: 14, minute: 0,
  timeZone: "America/New_York",
});

// Convert to Tokyo time
const meetingTokyo = meetingNY.withTimeZone("Asia/Tokyo");
// 2026-08-17T03:00:00+09:00[Asia/Tokyo]

// Convert to London time
const meetingLondon = meetingNY.withTimeZone("Europe/London");
// 2026-08-16T19:00:00+01:00[Europe/London]
```

## Intl.DateTimeFormat for locale-aware display

### Basic formatting

```javascript
const date = Temporal.PlainDate.from("2026-08-16");

// US English
new Intl.DateTimeFormat("en-US").format(date);
// "8/16/2026"

// British English
new Intl.DateTimeFormat("en-GB").format(date);
// "16/08/2026"

// German
new Intl.DateTimeFormat("de-DE").format(date);
// "16.8.2026"

// Japanese
new Intl.DateTimeFormat("ja-JP").format(date);
// "2026/8/16"

// Arabic (Eastern Arabic numerals)
new Intl.DateTimeFormat("ar-EG").format(date);
// "١٦/٨/٢٠٢٦"
```

### Detailed options

```javascript
const dt = Temporal.ZonedDateTime.from({
  year: 2026, month: 8, day: 16,
  hour: 14, minute: 30,
  timeZone: "America/New_York",
});

new Intl.DateTimeFormat("en-US", {
  dateStyle: "full",
  timeStyle: "long",
  timeZone: "America/New_York",
}).format(dt);
// "Sunday, August 16, 2026 at 2:30:00 PM EDT"

new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "long",
  timeStyle: "short",
  timeZone: "Europe/Paris",
}).format(dt);
// "16 août 2026 à 20:30"
```

### Relative time formatting

```javascript
const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

rtf.format(-1, "day");    // "yesterday"
rtf.format(2, "hour");    // "in 2 hours"
rtf.format(-3, "month");  // "3 months ago"

// Spanish
const rtfEs = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
rtfEs.format(-1, "day");  // "ayer"
rtfEs.format(2, "hour");  // "dentro de 2 horas"
```

## Storage and interchange best practices

```
Store:    Temporal.Instant (UTC) or ISO 8601 string
Transfer: ISO 8601 with timezone offset
Display:  Intl.DateTimeFormat with user's locale and timezone

Database:  TIMESTAMPTZ (PostgreSQL) / TIMESTAMP (MySQL with UTC)
API:       "2026-08-16T14:30:00Z" (ISO 8601)
Frontend:  Intl.DateTimeFormat(userLocale, { timeZone: userTZ })
```

## Anti-patterns

- **Hardcoded date formats** — using `MM/DD/YYYY` or `DD.MM.YYYY`
  string templates. Different locales use different separators, orders,
  and numbering systems. Use `Intl.DateTimeFormat` for all display
  formatting.
- **Storing local time without timezone** — saving "2026-08-16 14:30"
  without a timezone makes the timestamp ambiguous. Store UTC
  timestamps (`TIMESTAMPTZ`) and convert to the user's timezone for
  display.
- **Manual timezone offset math** — adding/subtracting hours for
  timezone conversion. This breaks during DST transitions. Use
  `Temporal.ZonedDateTime.withTimeZone()` or IANA timezone names.
- **Using legacy Date for arithmetic** — `Date` month arithmetic
  overflows silently (Jan 31 + 1 month = Mar 3). Temporal handles
  month boundaries correctly.

## Gotchas

- **Temporal polyfill size** — the `@js-temporal/polyfill` is ~40KB
  gzipped. For browsers without native support, consider loading it
  conditionally or using server-side rendering for date formatting.
- **Calendar systems** — `Intl.DateTimeFormat` supports non-Gregorian
  calendars (Islamic, Hebrew, Japanese Imperial) via the `calendar`
  option. Temporal supports these through `Temporal.PlainDate.from()`
  with a calendar parameter.
- **DST transitions** — during "fall back," a local time can exist
  twice. `Temporal.ZonedDateTime` handles this by defaulting to the
  earlier occurrence. Use the `disambiguation` option to control
  behavior (`compatible`, `earlier`, `later`, `reject`).
- **Locale data availability** — `Intl.DateTimeFormat` relies on ICU
  data, which varies by runtime. Node.js builds with `full-icu` have
  complete locale support; some minimal builds may lack certain
  locales.

## Verification

- All user-facing dates are formatted with `Intl.DateTimeFormat`.
- Timestamps are stored as UTC (`Temporal.Instant` or `TIMESTAMPTZ`).
- Time zone conversion uses IANA timezone names, not manual offsets.
- Date arithmetic uses `Temporal` types, not legacy `Date`.
- Application is tested with at least 3 locales and 3 time zones.
- DST transition edge cases are covered in tests.

## Related

- `documentation/docs/policies/i18n/icu-message-format-2-0.md`
- `documentation/docs/policies/i18n/machine-translation-post-editing-mtpe.md`
- `documentation/docs/policies/frontend/performance-optimization.md`

## Source URLs (verified 2026-08-16)

- Temporal API with JavaScript — https://jadjoubran.io/blog/javascript-temporal-api
- Temporal: The 9-Year Journey to Fix Time in JavaScript — https://bloomberg.github.io/js-blog/post/temporal/
- Proper Date Management in Modern JavaScript — https://blog.criticaldeveloper.com/posts/2026-07-07-proper-date-management-in-modern-javascript-timezones-temporal-intl-and-safer-ap/
- Node.js Date and Time Handling: Temporal Guide 2026 — https://www.hirenodejs.com/blog/nodejs-date-time-temporal-2026
