---
title: "IETF RFC 3339 Date and Time on the Internet Version Guide"
standard: "RFC 3339"
standard_status: "Proposed Standard"
publisher: "Internet Engineering Task Force (IETF)"
authors: "G. Klyne, C. Newman"
category: "reference"
subcategory: "internet-time-format"
canonical_url: "https://datatracker.ietf.org/doc/html/rfc3339"
obsoletes: "RFC 2616, RFC 2822 (date format sections)"
status: "approved"
classification: "public"
audience: "engineers"
last_reviewed: "2026-09-04"
---

# IETF RFC 3339 Date and Time on the Internet Version Guide

## 1. Purpose

RFC 3339 defines a profile of ISO 8601 for use in Internet protocols and data
interchange formats. It restricts the larger ISO 8601 grammar to the subset
that has been widely deployed and interoperated. This guide pins the ORCHORDS
adoption of RFC 3339 as the canonical timestamp format for all log, event,
and audit payloads.

## 2. Normative Scope

RFC 3339 specifies:

- `date-time` = `full-date "T" full-time`
- `full-date` = `date-fullyear "-" date-month "-" date-mday`
- `full-time` = `partial-time time-offset`
- `time-offset` = `"Z" | time-numoffset`
- `time-numoffset` = sign `":"` hour-minute
- `partial-time` = `time-hour ":" time-minute ":" time-second [time-secfrac]`

## 3. Reference Profile Adopted by ORCHORDS

| Feature | Decision | Rationale |
|---|---|---|
| Default zone | `Z` (UTC) | Single canonical representation |
| Separator | Uppercase `T` | RFC 3339 §5.6; lowercase `t` permitted but discouraged |
| Fractional seconds | Optional; when present, period decimal | Avoid comma confusion in CSV/log pipelines |
| Local time | Forbidden on the wire | Convert to UTC at edge |
| Leap second | Permitted only in `23:59:60` | RFC 3339 §4.3 — do not interpolate into next minute |
| Time-zone offsets | `±HH:MM` only; no seconds | RFC 3339 §4.3 — minutes granularity only |
| Unknown offset | Use `-00:00` (RFC 9557) | Distinguish "UTC but unverified" from "Z" |

## 4. Concrete Examples

```
1985-04-12T23:20:50Z
1985-04-12T23:20:50.123Z
1985-04-12T23:20:50+02:00
1985-04-12T23:20:50-08:00
1985-04-12T23:20:50.123456-08:00
```

## 5. Forbidden Constructs

- `1985-04-12 23:20:50Z` — space separator instead of `T`.
- `1985-04-12T23:20:50` — missing zone designator.
- `1985-04-12T23:20:50+0200` — missing colon in offset.
- `85-04-12T23:20:50Z` — two-digit year.
- `1985-04-12T23:20:50.000+02:00` — fractional + offset is acceptable, but second precision differs from millisecond; pick one.

## 6. Interop Notes

- **JSON**: emit strings, not numbers; numeric epoch seconds lose zone intent.
- **HTTP**: HTTP-Date (RFC 7231 §7.1.1.1) uses a different grammar (IMF-fixdate); do not substitute.
- **SMTP**: legacy RFC 2822 date format is not RFC 3339; both can coexist in the same system.
- **Time zone database**: pair with IANA tzdata; RFC 3339 does not name zones, only offsets.

## 7. Validation

ORCHORDS rejects payloads where any `date-time` field fails the ABNF in §2.
Recommended regex (extended, with optional fractional and offset):

```
^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]+)?(Z|[+-][01][0-9]:[0-5][0-9])$
```

## 8. Companion Documents

- **ISO 8601:2019** — superset; use for storage that may need richer intervals.
- **RFC 9557** — 2024 update adding `-00:00` unknown-offset and zone suffix support.
- **RFC 7231 §7.1.1.1** — IMF-fixdate for HTTP headers.

## 9. Version History

| Date | Action |
|---|---|
| 2002-07 | RFC 3339 published as Proposed Standard |
| 2024-08 | RFC 9557 supplements RFC 3339 with suffix syntax |
| 2026-09 | ORCHORDS reference card last reviewed |
