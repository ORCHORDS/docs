# The ICU Ethiopic Calendar and the Amete Mihret Era

The Ethiopic calendar is the liturgical and civil calendar of Ethiopia and Eritrea, with twelve 30-day months plus a 13th partial month (Pagume) of 5 or 6 days, an era offset from the Gregorian calendar of roughly seven to eight years, and new-year dates that shift against the Gregorian calendar. ICU implements it as `ethiopic` and `ethiopic-amete-alem` calendar variants. Software serving Ethiopian users — invoices, appointment systems, holiday calendars — must handle it correctly, and the era boundary behavior is where implementations most often go wrong. This article covers the calendar's structure in ICU, conversion semantics, era handling, and validation.

## Scope

This article addresses the Ethiopic calendar as implemented by ICU and specified through UTS #35 calendar elements and CLDR data: month lengths, the Pagume month, era handling (`AMETE_MIHRET` and the Amete Alem variant), leap-year computation, and conversion to and from Gregorian dates. It covers formatting and field-level APIs. It does not cover the Ethiopian clock convention (12-hour offset counting from dawn), time-zone policy, or the liturgical use of the calendar beyond structural facts.

## Workflow or implementation guidance

The Ethiopic calendar used by ICU has 13 months: the first twelve have 30 days each, and the thirteenth month (Pagume, locally Ṗagume) has 5 days in common years and 6 days in leap years. The new year (Meskerem 1) falls on September 11 in most Gregorian years and September 12 in Gregorian leap years preceding an Ethiopic leap year. The epoch relationship is that the Ethiopic era Amete Mihret ("year of mercy") begins roughly 8 years behind the Gregorian year count; concretely, the Gregorian year 2026 spans Ethiopic years 2018 (until Meskerem 1) and 2019 (from Meskerem 1 onward).

ICU exposes the calendar via calendar keyword selection: locale `am-ET-u-ca-ethiopic` requests the Ethiopic calendar with Amete Mihret era numbering, while `u-ca-ethiopic-amete-alem` uses the Amete Alem ("world") era, whose epoch is about 5,500 years before Amete Mihret and appears mainly in Ge'ez liturgical contexts. The two variants differ only in era year numbering; month and day structure is identical.

Implementation workflow:

1. Convert at the boundary. Store canonical dates in a proleptic Gregorian or absolute-day representation internally, and instantiate the Ethiopic calendar only for formatting, input parsing, and validation of user-entered dates.
2. When parsing user input, validate day-of-month against month length: days 1–30 for months 1–12, day 1–5 or 1–6 for Pagume depending on leap status. Rejecting day 6 in a common year requires knowing the leap rule: the Ethiopic leap year is roughly every fourth year, and its leap status aligns with the Amete Mihret year modulo 4 (year ≡ 3 mod 4 is leap in the convention ICU implements).
3. Beware era defaults in parsing: a user typing "2013" without an era means Amete Mihret. If your date widget shows era names, use CLDR era display names for `ethiopic` rather than inventing labels.
4. For ranges spanning the new year (September 11/12 boundary), do not convert by year arithmetic ("Gregorian year minus 7 or 8"); always convert through day-based APIs. The offset is 7 or 8 years depending on whether the date is before or after Meskerem 1, and a two-month window around the new year is where naive arithmetic defects cluster.
5. When formatting month names, use CLDR month names for `am` (Amharic) or `ti-ET` (Tigrinya); the months carry names like Meskerem, Tikimt, Hidar, Tahsas, Tir, Yekatit, Megabit, Miyazia, Ginbot, Sene, Hamle, Nehase, Pagume. Machine-generated labels like "Month 13" are an immediate quality defect.
6. If the UI mixes calendars (Ethiopic primary, Gregorian secondary in parentheses), format each with its own calendar-aware formatter and a locale that carries the right `-u-ca-` keyword; never hand-compose "Meskerem 1, 2019 (September 12, 2026)" from separate pieces without going through the same conversion API, or the two halves can disagree at the new-year boundary.

A worked example: Gregorian 2026-09-11 is Meskerem 1, 2019 EC (Ethiopic Calendar) because 2026 is not a Gregorian leap year. Gregorian 2027-09-11 is Meskerem 1, 2020 EC. Pagume 6, 2018 EC exists (2018 ≡ 2 mod 4 under ICU's convention is not leap; verify against the API rather than this arithmetic when implementing — the point of the example is that the boundary cases are exactly where implementations must rely on the library, not on folklore).

The Amete Alem variant deserves one operational note: ICU at various versions had incomplete data for `ethiopic-amete-alem` display names; test formatting in your pinned version before shipping it to liturgical users, and prefer `ethiopic` for civil applications.

## Controls

- Pin ICU/CLDR versions; calendar keyword handling and era display data have changed across releases, and civil applications should verify `u-ca-ethiopic` behaves identically after upgrades.
- Property-test conversion round trips: for every day in a 10-year window, convert Gregorian → Ethiopic → Gregorian and assert the original day is recovered; this catches off-by-one defects at Pagume and the September boundary without hand-derived expectations.
- Validate parsed Ethiopic dates against month lengths computed from the library, not from hardcoded 30/5/6 tables in application code.
- Snapshot-test formatted dates for fixed absolute days in `am-ET-u-ca-ethiopic` and `en-u-ca-ethiopic` to lock month-name and era rendering.
- Log user-entered dates in both calendars at the input boundary when validation fails, so support can see what the user meant.

## Validation evidence

- Calendar keywords, era definitions, and month data flow from UTS #35 (LDML) and CLDR calendar data published by the Unicode Consortium.
- The ICU User Guide's calendar chapters document the `ethiopic` and `ethiopic-amete-alem` variants, their eras, and construction by locale keyword.
- A reproducible check: construct an ICU date for an absolute day near September 11 in two successive years with `u-ca-ethiopic`, print the Ethiopic year, month, day; the year increments on Meskerem 1, not on January 1 — demonstrating that the library, not application arithmetic, must own the boundary.

## Failure modes and correction

- **Year-minus-seven arithmetic.** Symptom: documents dated one year off for dates between the Gregorian new year and Meskerem 1. Correct by converting through the calendar API.
- **Accepting Pagume 6 in common years.** Symptom: nonexistent dates stored and later rendered as the first day of the next year. Correct by validating day ranges from library-computed month lengths.
- **Wrong era variant.** Symptom: liturgical users see Amete Mihret years where they expect Amete Alem (or vice versa); the delta is about 5,500 years and unmistakable. Correct by selecting the variant explicitly via the calendar keyword.
- **Hand-built month labels.** Symptom: "13th month" strings or transliteration inconsistencies. Correct by using CLDR month names for the locale.
- **Mixed-calendar composition drift.** Symptom: primary and secondary date displays disagree by one day around the new year. Correct by deriving both displays from one converted instant.

## Limitations

- The Ethiopic calendar in ICU models the civil calendar; local practice on some holidays follows astronomical or liturgical computation outside the calendar's rule set.
- Historical dates before the era epoch are extrapolated proleptically and have limited practical meaning.
- Amete Alem display-name coverage varies by ICU version and locale; verify before relying on it.
- Time-of-day conventions in Ethiopia (dawn-based counting) are a formatting policy decision the calendar engine does not enforce.

## Canonical sources

- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML) — calendar elements and keywords: https://unicode.org/reports/tr35/
- Unicode, ICU User Guide — Calendar: https://unicode-org.github.io/icu/userguide/datetime/calendar/
