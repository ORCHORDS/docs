# The Persian Solar Hijri Calendar in ICU

The Persian (Solar Hijri, or Jalali) calendar is the civil calendar of Iran and Afghanistan (in its Persian-digit form), with a twelfth month (Esfand) that is 29 or 30 days depending on leap status, a new year (Nowruz) at the March equinox, and year numbering offset from the Gregorian year by 621 or 622. ICU implements it as the `persian` calendar. Systems serving Persian-language users — billing, scheduling, government-adjacent services — must convert and render these dates correctly, and equinox-based leap years make naive arithmetic impossible. This article covers the calendar's structure in ICU, conversion semantics, leap-year handling, and validation practice.

## Scope

This article addresses the Persian Solar Hijri calendar as implemented in ICU (`u-ca-persian`), including astronomical versus arithmetic (33-year cycle) variants, month structure, era conventions, and conversion to Gregorian. It covers formatting, parsing, and range validation. It does not cover the Islamic lunar Hijri calendar (a separate ICU calendar), Iranian time (IRST offset with no DST since 2022), or Persian digit shaping except where parsing interacts with it.

## Workflow or implementation guidance

The Persian calendar has 12 months: the first six (Farvardin, Ordibehesht, Khordad, Tir, Mordad, Shahrivar) have 31 days; the next five (Mehr, Aban, Azar, Dey, Bahman) have 30 days; and Esfand has 29 days in common years and 30 in leap years. Year 1 of the era corresponds to 622 CE; the year rolls over at Nowruz, the vernal equinox, which falls on March 20 or 21 in most years. Thus Gregorian 2026-03-20 or -21 begins 1405 SH; before the equinox it is still 1404.

Two leap determination traditions exist:

- **Astronomical (observational):** leap when the equinox falls before noon Tehran time in the Persian year's final assessment; this is the official Iranian rule and what the IANA/ICU astronomical sources approximate via precomputed tables.
- **Arithmetic (33-year cycle):** a fixed cycle approximation (leap years follow a 33-year pattern; e.g., years where `year mod 33 ∈ {1,5,9,13,17,22,26,30}` in one common variant) used by some libraries for simplicity; it agrees with the astronomical rule for long stretches and diverges occasionally near cycle boundaries.

ICU's `persian` calendar implements the astronomical table-based determination. The engineering consequence: leap status of a given year is a lookup, not a formula you should reimplement; and two libraries disagreeing about an Esfand 30 (e.g., whether 1403 SH had Esfand 30 — it did not; 1399 did) will disagree by a full day on date conversion for a window of users.

Implementation workflow:

1. Convert at boundaries: store instants (or absolute days) internally; instantiate `u-ca-persian` only for formatting and for validating user input in Persian form.
2. Parse with Persian digits when the audience uses them (۰۱۲۳۴۵۶۷۸۹, Extended Arabic-Indic U+06F0–U+06F9); normalization before parsing must map them to ASCII digits, and the locale `fa-IR` handles their rendering on the way out. Accepting only ASCII digits breaks real users typing with the standard Persian keyboard layout.
3. Validate day-of-month against month length from the library: days 1–31 for months 1–6, 1–30 for months 7–11, 1–29/30 for Esfand per computed leap status. Never accept "Esfand 30" without checking the year.
4. Do not compute the year offset arithmetically ("Gregorian minus 621/622"). Correct conversion requires the equinox day; the two-month window around Nowruz is where naive subtraction mislabels the year. Example: 2026-03-19 is 1404/12/28 SH; 2026-03-21 is 1405/01/01 SH. An arithmetic implementation must at minimum know the equinox date, at which point it is doing table lookup anyway.
5. Month names come from CLDR for the locale: `fa-IR` month names (فروردین … اسفند); `en` with `u-ca-persian` gives transliterated names (Farvardin … Esfand). Never hardcode both spellings; locale data owns them.
6. Era display: the `persian` calendar in ICU uses the Anno Persico era; most civil UIs omit era text entirely (year numbers are unambiguous in context). If shown, use CLDR era names, not invented "AP" suffixes — though "AP" (After Persico?) is sometimes seen in English transliteration; prefer omitting.
7. Afghanistan uses the same Solar Hijri structure (also `u-ca-persian`) with Pashto month names in `ps-AF` locale data; do not assume Iran-specific month names for Afghan users.

A worked example: a subscription billing system generating renewal notices for Persian users must format "renews on 1405/01/15" and compute the Gregorian instant (2026-04-04). Doing the reverse from a Gregorian anchor ("renews in 15 days") then formatting in Persian requires exactly one conversion through the library; any shortcut that formats a Gregorian date with a Persian year label computed by subtraction will be wrong for notices generated between January 1 and Nowruz.

## Controls

- Pin ICU/CLDR and thereby the embedded Persian calendar tables; document the pin alongside other locale data pins.
- Property-test round trips across a ±20-year window around today: for every absolute day, convert Gregorian → Persian → Gregorian and assert identity; separately assert Esfand day counts per year match the library's own `getMaximum(field)` for DAY_OF_MONTH.
- Parse-test with Persian-digit and ASCII-digit inputs, with and without the Persian date separator (`/` U+002F and the Arabic decimal separator variants users type).
- Snapshot format tests for fixed instants in `fa-IR-u-ca-persian` (Persian names, Persian digits) and `en-u-ca-persian` (transliterated names) at pinned versions.
- Where third-party systems convert Persian dates (reporting pipelines, spreadsheets), record the library and version next to the data; cross-library disagreement is expected near leap boundaries and must be detected, not averaged.

## Validation evidence

- The `persian` calendar keyword, era, month lengths, and table-driven leap determination are implemented in ICU and documented in the ICU User Guide calendar chapters; the calendar data derives from astronomical tables aligned with the IANA time zone database distribution context.
- CLDR locale data for `fa` and `ps` supplies month names and digit systems per UTS #35 (LDML).
- A reproducible check: in a pinned ICU, compare days-in-year for successive Persian years across 1390–1410; the pattern shows Esfand 30 occurrences exactly in the astronomical leap years (e.g., 1399), and any implementation claiming a different leap year diverges from ICU's tables — evidence you must delegate, not recompute.

## Failure modes and correction

- **Subtraction-based year math.** Symptom: all dates between January 1 and Nowruz show the wrong Persian year. Correct by library conversion only.
- **Fixed-cycle leap assumption.** Symptom: occasional one-day errors on Esfand 29/30 and after-Nowruz conversions for specific years. Correct by removing the arithmetic rule and deferring to ICU tables.
- **Rejecting Persian digits.** Symptom: users cannot type their birthdate. Correct by digit normalization in the parse path.
- **Hardcoded month names.** Symptom: Afghan users see Iranian names (or vice versa); typographic mismatches in official documents. Correct by locale-driven names.
- **Validating Esfand 30 without year context.** Symptom: nonexistent dates stored, later rendered as day 1 of the new year. Correct by year-aware month-length validation.

## Limitations

- Historical Persian dates (pre-1925 adoption of the modern calendar) follow proleptic extrapolation and do not match historical Jalali practice everywhere.
- ICU's tables follow the astronomical determination; communities or systems standardized on the 33-year arithmetic calendar will disagree in rare years; document which rule your product follows.
- Afghanistan's weekday/weekend and month-name conventions differ from Iran's; locale selection must distinguish `fa-IR`, `ps-AF`, and `fa-AF`.
- Equinox-based rollover means Nowruz can fall on March 20 or 21 (rarely 19 or 22 in extreme cases); any UI copy promising a fixed Gregorian date is wrong by construction.

## Canonical sources

- Unicode, ICU User Guide — Calendar (persian calendar variants and leap determination): https://unicode-org.github.io/icu/userguide/datetime/calendar/
- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML) — calendar keywords and month name data: https://unicode.org/reports/tr35/
