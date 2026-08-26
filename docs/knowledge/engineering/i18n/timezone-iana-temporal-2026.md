# timezone-iana-temporal-2026

**Issue:** A meeting is scheduled for "March 29 2026 02:00" in `Europe/London`. The meeting never happens because the time doesn't exist — the UK clocks spring forward from 01:00 to 02:00 that night. The user sees a 404 from the calendar. The team debugs for hours.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

JavaScript's legacy `Date` object is mutable, has no real timezone awareness, and parses inconsistently across engines. The Temporal API reached TC39 Stage 4 in March 2026 and is now part of the ES2026 specification, shipping natively in Chrome 144, Firefox 139, and Edge 144. Safari support is in Technology Preview.

The rule that prevents 90% of date bugs: **store UTC ISO 8601 strings on the server, format on the client with the user's IANA timezone**.

## Root cause

A date in software encodes four things at once: a moment on the absolute timeline (a UTC instant), a calendar interpretation, a wall-clock time, and the timezone rules connecting the last three to the first. The legacy `Date` collapses all four into a single mutable millisecond timestamp that pretends to be in the local zone. This breaks under DST, half-hour/quarter-hour timezones, historical offset changes, and timezones that countries abandon.

The IANA Time Zone Database releases multiple updates per year — `tzdb 2026a` shipped in April 2026 — and any system that hard-codes offsets instead of reading from this database drifts out of step within months.

## The Temporal API types

| Type | Represents | Example |
|---|---|---|
| `Temporal.Instant` | A UTC moment, no calendar | `2026-05-22T08:00:00Z` |
| `Temporal.ZonedDateTime` | An instant in a named timezone | `2026-05-22T10:00:00+02:00[Europe/Berlin]` |
| `Temporal.PlainDateTime` | A wall-clock date and time, no zone | `2026-05-22T10:00:00` |
| `Temporal.PlainDate` | A calendar date, no time, no zone | `2026-05-22` |
| `Temporal.PlainTime` | A clock time, no date, no zone | `10:00:00` |
| `Temporal.PlainYearMonth` | Useful for billing cycles, credit cards | `2026-05` |
| `Temporal.Duration` | An amount of time | `P1Y2M3DT4H5M6S` |

`Temporal.Instant` is just a nanosecond timestamp. `Temporal.ZonedDateTime` wraps an `Instant` with a named IANA timezone so arithmetic, formatting, and "what's the wall-clock time" all work correctly across DST and offset changes.

## The five rules

**Store in UTC, in ISO 8601 format.** `2026-05-22T08:00:00Z` on the wire and in the database. No offsets, no ambiguity, no engine-specific parsing.

**Pass UTC through the stack.** Server returns UTC. Frontend stores UTC. Caches store UTC. State managers store UTC. The string never gets reinterpreted in transit.

**Render in the user's timezone, at the latest possible moment.** Only when the date is about to hit the DOM does the code ask "what timezone is the user in, and what locale do they expect?" — and converts.

**Standardise on ISO 8601 with `Z`.** Every timestamp on the wire ends in `Z`. Anything else is a bug ticket waiting to be filed. APIs reject offsets, return UTC, and let the client convert.

**Carry the user's IANA zone as a profile field.** Don't infer it on every request. Ask once (or detect on first login via `Intl.DateTimeFormat().resolvedOptions().timeZone`), store it, send it with the user's session. Then every render has the zone available without guessing.

## The Temporal API by example

```javascript
// Current instant
const now = Temporal.Now.instant().toString();
// → "2026-08-10T14:30:00.123456789Z"

// Schedule a meeting 9 AM next Tuesday in Europe/Berlin
const meeting = Temporal.ZonedDateTime.from({
  timeZone: "Europe/Berlin",
  year: 2026, month: 8, day: 12,
  hour: 9, minute: 0
});
// → "2026-08-12T09:00:00+02:00[Europe/Berlin]"

// Add 1 day — DST-safe
const tomorrow = meeting.add({ days: 1 });
// If a DST change happens, Temporal adjusts automatically

// Convert to another zone for display
meeting.withTimeZone("America/New_York")
// → "2026-08-12T03:00:00-04:00[America/New_York]"

// Format for user
new Intl.DateTimeFormat("en-US", {
  dateStyle: "full", timeStyle: "short",
  timeZone: "America/New_York"
}).format(meeting.toInstant().epochMilliseconds)
// → "Tuesday, August 12, 2026 at 3:00 AM"
```

## The DST gap problem

Some moments simply don't exist. On 29 March 2026, UK clocks spring forward from 01:00 to 02:00; `01:30` doesn't exist. `Date` returns bizarre values. `Temporal.ZonedDateTime` requires an explicit choice:

- `reject` — throws
- `earlier` — picks the time before the gap
- `later` — picks the time after the gap (default for `compatible`)

Arithmetic on an existing `ZonedDateTime` handles gaps automatically. Only construction needs the choice.

## The recurring event pattern

Store recurring events as wall-clock time in a named zone, not as UTC instants:

```javascript
// Wrong: stored as UTC instant
const weeklyMeeting = new Date("2026-08-12T09:00:00Z");
// DST change in October shifts the wall-clock time

// Right: stored as wall-clock in named zone
const weeklyMeeting = Temporal.ZonedDateTime.from({
  timeZone: "Europe/Berlin",
  year: 2026, month: 8, day: 12,
  hour: 9
});
// Materialise instants for each occurrence at query time
```

This pattern is the only correct way to handle recurring events across DST boundaries.

## The legacy `Date` migration

Don't migrate the entire codebase in one sprint. Start with the parts that hurt most:

1. Audit every `new Date()` call in the codebase; classify as instant, date, or wall-clock time
2. Replace the most bug-prone call sites (timezone-sensitive scheduling, date arithmetic, billing intervals) with Temporal types
3. Introduce a factory module so all new code uses Temporal
4. Add a linter rule (`eslint-plugin-temporal`) that flags `new Date()` outside legacy adapter code
5. Set up a single integration test that asserts a known date/time produces the expected ISO string in a non-UTC timezone

## The cross-engine support matrix

| Engine | Temporal support |
|---|---|
| Chrome 144+ | Native (January 2026) |
| Firefox 139+ | Native (May 2025) |
| Edge 144+ | Native (January 2026) |
| Safari | Technology Preview (stable later 2026) |
| Node.js 24+ | Behind flag |
| Node.js 26 | Native by default |

For older browsers, use `@js-temporal/polyfill` — identical API, automatically deactivates as native support lands.

## Verification

The tell that timezone handling is working:

- Every timestamp on the wire ends in `Z`; no offsets, no ambiguous strings
- The user's IANA zone is stored as a profile field, not inferred per request
- Date math (add days, add months) uses `Temporal.ZonedDateTime` in a named zone, not `Date` arithmetic
- Recurring events are stored as wall-clock time in a named zone, not as UTC instants
- DST transitions are tested (the `01:30 doesn't exist` case)
- The Temporal API is the default for new code; `Date` is a serialisation primitive

The tell it isn't:

- "We store everything in UTC" but format with `toLocaleString` and the server's local zone
- A meeting scheduled across DST shows up at the wrong wall-clock time
- The legacy `Date` is used for arithmetic, billing cycles, or scheduling
- The team cannot name the difference between `Temporal.Instant` and `Temporal.ZonedDateTime`

## Gotchas

- **`Date` is a serialisation primitive, not a working type.** Mutable, no real timezone, engine-specific parsing.
- **Store the IANA zone in the user's profile.** Don't infer per request; carry it with the session.
- **Use `Temporal.ZonedDateTime` for scheduling, billing, recurring events.** `Temporal.Instant` is for storage and cross-timezone comparison.
- **DST gaps produce non-existent times.** Explicit choice required at construction; arithmetic handles automatically.
- **The IANA database updates multiple times per year.** Pin your runtime/library to the latest; hard-coded offsets drift.
- **`Temporal.Polyfill` deactivates when native support lands.** Don't pin to a specific version; let it resolve to native.
- **The wall-clock-in-zone pattern for recurring events.** Store as `ZonedDateTime` in a named zone; materialise instants at query time.

## Related

- `i18n/locale-negotiation.md` — locale affects which timezone + number formatting applies
- `i18n/icu-message-format.md` — date/time formatting in user-facing strings
- `i18n/number-currency-formatting-2026.md` — paired number formatting

## Source URLs (verified 2026-08-10)

- https://crosscheck.cloud/blogs/handling-dates-and-timezones-javascript/
- https://byteiota.com/javascript-temporal-api-migrate-off-date-in-2026/
- https://the-practical-developer.online/posts/temporal-api-javascript-date-time-production/
- https://www.thingsaboutweb.dev/en/posts/temporal-api
- https://www.w3schools.com/js/js_temporal_zoneddatetime.asp
