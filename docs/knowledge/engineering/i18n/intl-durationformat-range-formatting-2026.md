# intl-durationformat-range-formatting-2026

**Issue:** An app hardcodes duration strings like `` `${h} hours ${m} min` `` and date ranges like `` `${start} - ${end}` ``, which break instantly in other locales: German wants "1 Stunde, 30 Minuten" with different pluralization and separators, and a same-month range should collapse to "5.–9. Januar" in de or "1月5日～9日" in ja rather than repeating the month. `Intl.DurationFormat` (Baseline newly available March 2025) and `Intl.DateTimeFormat.prototype.formatRange` solve both natively. This article is the 2026 reference for adopting them and retiring hand-rolled duration/range formatting.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 facts about Intl.DurationFormat

1. **Baseline "newly available" since 2025-03-04.** Chrome/Edge 129 (Sept 2024), Safari 18.2 (late 2024), Firefox 136 (March 2025). Roughly ~82% global support at baseline time — polyfill or feature-detect for older Safari/Enterprise Chromium.
2. **Not in Node.js yet.** Despite shipping in V8, Node's ICU wiring lags (nodejs/node issue #<number>). Do not share a bare `Intl.DurationFormat` call between browser and server code without detection; use `humanize-duration` or a duration-message ICU pattern server-side.
3. **It accepts plain duration-like objects.** `df.format({ hours: 1, minutes: 30 })` — keys are `years, months, weeks, days, hours, minutes, seconds, milliseconds, microseconds, nanoseconds`. No Date math needed.
4. **It is designed for `Temporal.Duration`.** When Temporal ships, the same formatter takes `Temporal.Duration` instances directly; writing formatting code against the duration-like shape now is forward-compatible.
5. **Zero-valued fields are omitted by default.** `format({ hours: 0, minutes: 30 })` yields just "30 minutes". That is usually what you want; it also means tests should not assert on full field lists.

## The 5 formatting patterns

1. **Long human durations.** `new Intl.DurationFormat('en', { style: 'long' }).format({ days: 1, hours: 2, minutes: 34 })` → "1 day, 2 hours, 34 minutes". Style options are `long`, `short`, `narrow`, plus `digital` for stopwatch-style time.
2. **Digital/timer display.** `{ style: 'digital' }` renders time units clock-style for media players and countdowns, respecting the locale's time conventions instead of your hardcoded `HH:MM:SS`.
3. **Fractional seconds.** `fractionalDigits: 2` controls sub-second precision for sports/lap timers without manual millisecond-to-string math.
4. **Date ranges via `formatRange`.** `new Intl.DateTimeFormat('en', { dateStyle: 'medium' }).formatRange(start, end)` elides identical fields: same-month ranges collapse to "Jan 5 – 9, 2026"; German renders "5.–9. Jan. 2026" with its own dash and ordinal dots. One call replaces all hand-built range logic.
5. **Styled ranges via `formatRangeToParts`.** When you need the month bolded or the dash styled, `formatRangeToParts` (like `formatToParts`) returns typed segments — never re-implement range collapsing with string surgery.

## The 5 migration steps from hand-rolled formatting

1. **Inventory the call sites.** Grep for `/(\d+)\s*(h|min|hr|hour|minute|sec)/i` template patterns and ` - ` joins between two formatted dates; each is a migration candidate.
2. **Feature-detect once.** `const canDuration = typeof Intl.DurationFormat === 'function'` and fall back to an ICU message with plural rules (`{h, plural, one {# hour} other {# hours}}`) — which you should already have for translated UI strings.
3. **Replace duration display first, ranges second.** Durations are pure wins (no locale data beyond CLDR); ranges additionally need snapshot review because elision differs per locale.
4. **Keep raw numbers upstream.** Store seconds/minutes as numbers and format only at render; `DurationFormat` takes the object form, so a `secondsToDuration(totalSeconds)` helper feeding `{ hours, minutes, seconds }` keeps arithmetic clean.
5. **Snapshot golden outputs per locale.** Assert `de`, `ja`, `ar` outputs in unit tests — durations pluralize ("1 minute" vs "2 minutes" vs German "1 Minute"/"2 Minuten") and the formatter is the component doing that work now.

## The 5 gotchas

- **`Intl.DurationFormat is not a constructor` on Node.** Server-side rendering will crash if you assume parity with browsers; gate it (issue #<number> tracks Node support).
- **Digital style is time-units only.** Weeks/months in `digital` style are ignored/error-prone; convert to hours/days first or use `long`.
- **Range elision is locale-decided.** Do not assert that "the month appears once" — some locales elide differently, and cross-year ranges keep both years. Test the actual locales you ship.
- **The minus/dash glyph varies.** `formatRange` picks the correct separator per locale; your CSS letter-spacing tuned for ASCII " - " will misalign for "–" or "～".
- **Formatter reuse still applies.** Constructing `Intl.DurationFormat`/`DateTimeFormat` per cell in a table is a measurable cost; cache per locale+options key, exactly as with `NumberFormat`.

## Source URLs (verified 2026-08-15)

- https://web.dev/blog/intl-durationformat-baseline
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DurationFormat
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/formatRange
- https://github.com/nodejs/node/issues/57414
- https://web-platform-dx.github.io/web-features-explorer/features/intl-duration-format/

## Related

- `i18n/relative-time-formatting.md` — "3 hours ago" vs "1 hour 30 minutes elapsed" are sibling needs
- `i18n/date-formatting-intl.md` — base `DateTimeFormat` usage
- `i18n/timezone-iana-temporal-2026.md` — Temporal.Duration integration
