---
title: "ISO 8601 — Date and Time Format Standard"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "engineering"
status: "approved"
iso-refs: ["ISO 8601:2019"]
---

# ISO 8601 — Date and Time Format

## Purpose

This document defines how all dates, times, durations, and intervals MUST be represented across Beetle Studio documentation, source code, logs, metadata, APIs, and user-facing displays.

ISO 8601 is the international standard for unambiguous date and time representations, first published in 1988, revised in 2004 and again in 2019 (split into ISO 8601-1:2019 and ISO 8601-2:2019).

## Scope

Applies to:
- All documentation files in this repository
- Commit messages and changelogs
- API request/response payloads
- Log output and telemetry timestamps
- Configuration files
- Release notes and version metadata
- Build artifact naming
- User-facing date/time displays

## Date Formats

### Calendar Date (most common)

| Format | Example | Use Case |
|--------|---------|----------|
|  |  | Extended format (REQUIRED in docs) |
|  |  | Basic format (acceptable in filenames) |
|  |  | Reduced precision (month only) |
|  |  | Reduced precision (year only) |

### Ordinal Date

| Format | Example | Meaning |
|--------|---------|---------|
|  |  | Day 172 of year 2026 |

Used in astronomy, aviation, and build numbering.

### Week Date

| Format | Example | Meaning |
|--------|---------|---------|
|  |  | Saturday of week 25, 2026 |
|  |  | Week 25 of 2026 |

Week numbering: Week 01 is the week containing the first Thursday of the year (ISO week-numbering year).

## Time Formats

ISO 8601 uses 24-hour clock notation exclusively.

| Format | Example | Notes |
|--------|---------|-------|
|  |  | Extended (REQUIRED in docs) |
|  |  | Basic format |
|  |  | Reduced precision |
|  |  | Millisecond precision |
|  |  | Microsecond precision |

Midnight:  (start of day) or  (end of day, equivalent to  of the next day).

## Combined Date and Time

The letter  separates date and time components:



## Time Zone Designators

| Designator | Example | Meaning |
|------------|---------|---------|
|  |  | UTC (Coordinated Universal Time) |
|  |  | UTC offset (ahead) |
|  |  | UTC offset (behind) |
|  |  | Reduced precision offset |

**Rule:** All timestamps in logs, APIs, and metadata MUST include a timezone designator. UTC () is preferred for storage; local time with offset for user display.

## Durations

Format: 

| Example | Meaning |
|---------|---------|
|  | 3 years |
|  | 6 months |
|  | 4 days |
|  | 12 hours |
|  | 30 minutes |
|  | 45 seconds |
|  | 1 year, 2 months, 3 days, 4 hours, 5 minutes, 6 seconds |
|  | Half a year (decimal allowed) |

Alternative format using weeks:  (2 weeks). Weeks cannot be combined with other designators.

## Time Intervals

Two points in time separated by :

| Format | Example |
|--------|---------|
| Start/End |  |
| Start/Duration |  |
| Duration/End |  |

## Repeating Intervals

Format:  where  is the number of repetitions.

| Example | Meaning |
|---------|---------|
|  | Repeat 3 times, starting 2026-01-01, every month |
|  | Repeat indefinitely every day |

## Application Rules for Beetle Studio

### Source Code


### Git Tags


### Log Output


### Filenames with Dates


### Changelog Entries


## Sorting

ISO 8601 dates sort correctly in lexicographic (alphabetical) order because the most significant component (year) appears first. This is a key advantage over locale-dependent formats.

## Prohibited Formats

The following formats MUST NOT be used in any Beetle Studio artifact:

| Prohibited | Reason |
|-----------|--------|
|  | Ambiguous (US format) |
|  | Ambiguous (EU format) |
|  | Locale-dependent |
|  | Locale-dependent |
|  | Ambiguous century |
|  | 12-hour format |

## References

- [ISO 8601:2019 (ISO official)](https://www.iso.org/iso-8601-date-and-time-format.html)
- [W3C Date and Time Formats (ISO 8601 profile)](https://www.w3.org/TR/NOTE-datetime)
- [ISO 8601 Wikipedia](https://en.wikipedia.org/wiki/ISO_8601)
- [RFC 3339 (Internet profile of ISO 8601)](https://www.ietf.org/rfc/rfc3339.txt)
