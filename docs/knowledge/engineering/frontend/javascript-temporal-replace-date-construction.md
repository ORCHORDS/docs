# Javascript Temporal Replace Date Construction

## Scope

Replacing `new Date()` construction and the mutable `Date` type with the `Temporal` API in application code. Covers choosing the right Temporal type for each date/time concept, constructing values without parsing ambiguity, arithmetic and comparison without mutation, time-zone correctness for scheduled events, and the migration sequence for a codebase. Excludes Intl formatting integration beyond where it applies to migration, and excludes calendar systems other than ISO 8601 except as a limitation note.

## Workflow or implementation guidance

The `Date` type combines four distinct concepts into one mutable object — an instant, a wall-clock date, a wall-clock time with zone, and a local date-time without zone — which is why `new Date('2026-03-01')` and `new Date(2026, 2, 1)` disagree by a day and a zone. Temporal separates them into types chosen by what the value means, not by how it is stored.

- A moment in time (an event that happened, a log timestamp): `Temporal.Instant`.
- A calendar date with no time or zone (a birth date, a due date): `Temporal.PlainDate`.
- A wall-clock date and time with no zone (a meeting defined in one location's local terms): `Temporal.PlainDateTime`.
- A date-time tied to a zone (a scheduled calendar entry): `Temporal.ZonedDateTime`.
- A time of day (an office-hours rule): `Temporal.PlainTime`.

Construction replaces the two ambiguous `Date` forms with explicit, named ones.

```js
// Before: parsing is implementation-sensitive across separators
const legacy = new Date('03/01/2026'); // month/day/year in one engine's locale rules

// After: ISO-only parsing, unambiguous
const due = Temporal.PlainDate.from('2026-03-01');
const start = Temporal.PlainTime.from('09:30');
const meeting = Temporal.ZonedDateTime.from('2026-03-01T09:30[America/New_York]');
const now = Temporal.Now.instant();
```

`Temporal.PlainDate.from` accepts ISO 8601 strings and rejects non-ISO input rather than guessing; use the `from` options bag to relax or constrain overflow behavior when converting user input. The legacy numeric constructor form maps to property bags:

```js
// Before: new Date(2026, 2, 1)  // month is zero-indexed
// After: no zero-indexed months
const release = Temporal.PlainDate.from({ year: 2026, month: 3, day: 1 });
```

Arithmetic is functional rather than mutating, removing the class of bugs where a shared `Date` is shifted in place.

```js
const trialEnd = due.add({ days: 30 });
const daysLate = Temporal.PlainDate.compare(today, due) > 0
  ? today.since(due, { largestUnit: 'day' }).days
  : 0;
```

Calendar arithmetic respects units: `add({ months: 1 })` on `PlainDate` clamps month-end overflow per the overflow option, and `since` returns a duration in requested units rather than a millisecond count that callers divide by heuristics.

Zones are the largest correctness win. A `ZonedDateTime` keeps the time zone and, for future events, the offset rules in effect at that local time, so a 9:30 New York meeting stays 9:30 across DST boundaries when the zone shifts.

```js
const meeting = Temporal.ZonedDateTime.from('2026-03-01T09:30[America/New_York]');
const utcInstant = meeting.toInstant(); // correct offset for that date
```

Migration sequence: inventory `new Date` and `Date.parse` call sites; classify each into the five concepts; introduce a boundary module that constructs the correct Temporal type and converts to legacy `Date` only at the edges (storage serialization, third-party components) via `Temporal.Instant.prototype.toString` and epoch milliseconds; then migrate call sites inward. Keep persistence as ISO 8601 strings (with offset and zone identifier where the concept requires it) rather than epoch numbers, because epoch silently drops the zone information that `ZonedDateTime` exists to preserve.

## Controls

- One boundary module owning construction: all parsing and `from` options live there, so string-format decisions are reviewable in one file.
- Type-selection rule per field documented in the domain model: instant for events, plain date for anniversary-style fields, zoned date-time for scheduled entries.
- ISO 8601 string serialization with explicit `toString` options where rounding or precision matters.
- Overflow behavior chosen explicitly at construction (`constrain` for user input, `reject` for system values) instead of relying on defaults.
- Comparison via `Temporal.PlainDate.compare` / `Temporal.Instant.compare` rather than subtraction, which keeps intent visible and avoids sign-convention mistakes.

## Validation evidence

- Property-based tests comparing migrated logic against a fixture table of known date/zone cases: month-end clamping, DST spring-forward and fall-back days, and end-of-year arithmetic.
- Snapshot persistence round-trips: construct, serialize, re-parse, and assert equality for each Temporal type in use, proving the serialization format preserves the concept.
- Regression suite over migrated call sites with frozen clock injections, since `Temporal.Now.instant()` is the injectable seam replacing monkey-patched `Date.now`.
- Cross-check DST-sensitive scheduling outputs against the operating system's zone database for the deployment year, in CI, with the zone data version pinned.

## Failure modes and correction

- Storing `Temporal.Instant` epoch milliseconds for a scheduled future event: the zone is lost and the event drifts an hour across DST. Store the `ZonedDateTime` ISO string including the zone identifier.
- Constructing `PlainDateTime` and treating it as a moment: without a zone it is not a point in time; convert with `toZonedDateTimeISO` or carry `ZonedDateTime` from the start.
- Parsing user-typed non-ISO strings with `from` throws where `Date` guessed. Validate and normalize input before `from`, and surface the error rather than falling back to `new Date`.
- Assuming `since` returns calendar units by default: it returns units per the `largestUnit` option; specify it, or day counts silently include or exclude month boundaries differently than the old millisecond math.
- Time zone identifiers from the host (`Temporal.Now.timeZone()`) used to interpret stored data: the stored value's zone wins; the host zone is only a default for input.
- Legacy conversion edges reintroducing ambiguity: converting to `Date` via epoch milliseconds and back drops sub-second precision and zone; route conversions through the boundary module only.

## Limitations

- `Temporal` is a large proposal; engine availability reached general availability progressively, so a polyfill is required for older support floors and carries a nontrivial bundle cost — load it selectively if bundle size matters.
- Intl formatting integration goes through the standard formatter; rich localized calendar displays beyond ISO require that layer.
- Non-ISO calendar systems (for example Hebrew or Islamic calendars) are supported through explicit calendar objects, but interop with legacy code that assumes Gregorian needs care at the boundary.
- Third-party libraries that accept or return `Date` force conversion at every integration point; the boundary-module pattern mitigates but does not remove this.
- Parsing is strict by design: no locale-ordered formats, so human-facing input needs a parsing/validation step that Temporal itself does not provide.

## Canonical sources

- TC39, Temporal proposal: https://tc39.es/proposal-temporal/
- MDN, `Temporal` reference: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Temporal
- MDN, `Temporal.PlainDate`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Temporal/PlainDate
- MDN, `Temporal.ZonedDateTime`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Temporal/ZonedDateTime
