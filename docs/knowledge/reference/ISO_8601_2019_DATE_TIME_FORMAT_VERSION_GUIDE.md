---
title: "ISO 8601:2019 Date and Time Format Version Guide"
standard: "ISO 8601"
standard_edition: "2019-12 (4th edition)"
publisher: "International Organization for Standardization (ISO)"
category: "reference"
subcategory: "calendar-time-format"
canonical_url: "https://www.iso.org/iso-8601-date-and-time-format.html"
status: "approved"
classification: "public"
audience: "engineers"
last_reviewed: "2026-09-04"
---

# ISO 8601:2019 Date and Time Format Version Guide

## 1. Purpose

ISO 8601 is the international standard for the exchange of date- and time-related
data. It defines unambiguous representations of dates, times, time durations,
time intervals, and recurring time intervals. This guide pins the ORCHORDS
reference card to the fourth edition (ISO 8601:2019-12), which superseded the
2004 third edition and the 2000 second edition.

## 2. Normative Scope

ISO 8601:2019 specifies:

- Calendar dates (year, month, day) with proleptic Gregorian rules.
- Times of day (hour, minute, second) with optional fractional seconds.
- Combined date-time representations.
- Durations (`P[n]Y[n]M[n]DT[n]H[n]M[n]S`).
- Time intervals (start/end with a solidus separator).
- Recurring intervals using `R[n]/` prefix.
- Expanded representations with explicit sign and year length (0, 4, or 6 digits).

## 3. Reference Profile Adopted by ORCHORDS

| Feature | Decision | Rationale |
|---|---|---|
| Calendar | Proleptic Gregorian | Required for fixed-format interchange |
| Date format | `YYYY-MM-DD` (extended) | Most interoperable, RFC 3339 compatible |
| Time format | `HH:MM:SS[.fff]` (extended) | RFC 3339 compatible |
| Combined | `YYYY-MM-DDTHH:MM:SSZ` | UTC indicator `Z` required for storage |
| Fractional seconds | 3 digits (milliseconds) | Sufficient for most telemetry |
| Year length | 4 digits for years 0000-9999 | Default; expanded form reserved for far-future |
| Ordering | Big-endian (most significant first) | Sortable as string |
| Separator | Hyphen for date, colon for time, `T` between | ISO 8601:2019 §4.3 |

## 4. Quick Reference Grammar

```
date                = year "-" month "-" day
time                = hour ":" minute ":" second [frac]
date-time           = date "T" time [time-zone]
duration            = "P" [dur-date] ["T" dur-time]
time-zone           = "Z" | offset
offset              = ("+" | "-") hour ":" minute
year                = [sign] digit{4} | [sign] digit{6}
```

## 5. Concrete Examples (Accepted by ORCHORDS Validators)

```
2026-09-04                       (date only)
2026-09-04T14:30:00Z              (UTC date-time)
2026-09-04T14:30:00.123Z         (UTC with milliseconds)
2026-09-04T14:30:00+02:00        (CEST)
+002026-09-04T14:30:00Z          (expanded year, far future)
P3Y6M4DT12H30M5S                 (duration: 3y 6m 4d 12h 30m 5s)
2026-09-04T14:30:00Z/P1H         (interval: 1 hour starting at)
R5/2026-09-04T00:00:00Z/P1D      (5 daily recurrences)
```

## 6. Forbidden Constructs

- Local time without offset (e.g. `2026-09-04T14:30:00`) — never store; always serialize with `Z` or explicit offset.
- Two-digit years — disallowed; the 2004 edition deprecated them and 2019 removed them as a recommended form.
- Comma as decimal separator — ISO 8601:2019 §4.2.2.4 specifies full stop (period) for fractional seconds.

## 7. Version History

| Edition | Year | Notes |
|---|---|---|
| 1st | 1988 | ISO 8601:1988 |
| 2nd | 2000 | ISO 8601:2000 |
| 3rd | 2004 | ISO 8601:2004 |
| 4th | 2019 | ISO 8601:2019 — current; clarifies expanded representations and time-zone offsets |

## 8. Related Standards

- **IETF RFC 3339** — subset of ISO 8601 for Internet protocols; required reading alongside this card.
- **IETF RFC 9557** — extends RFC 3339 with `-u` and `-t` suffixes for unknown local offset and zone abbreviation.
- **IANA tzdata** — authoritative time-zone database (`tzdb`); pair with ISO 8601 to obtain civil time from UTC.

## 9. Validation

ORCHORDS validators accept any input that parses against the EBNF in §4 and
reject everything else with HTTP 400. Implementations MUST emit the
`date-time` form with the `Z` suffix when the timestamp is in UTC.
