---
title: "IANA Time Zone Database (tzdb) 2026a Version Guide"
standard: "IANA tzdata"
standard_release: "2026a"
publisher: "Internet Assigned Numbers Authority (IANA)"
maintainers: "Time Zone Database Working Group (tzdb.org)"
category: "reference"
subcategory: "time-zone-database"
canonical_url: "https://www.iana.org/time-zones"
data_repository: "https://github.com/eggert/tz"
status: "approved"
classification: "public"
audience: "engineers"
last_reviewed: "2026-09-04"
---

# IANA Time Zone Database (tzdb) 2026a Version Guide

## 1. Purpose

The IANA Time Zone Database (often called `tzdata` or `tzdb`) is the
authoritative source for civil time-zone information. It is referenced by
virtually every major operating system, language runtime, and calendar
application. This guide pins ORCHORDS adoption of the 2026a release as the
authoritative zone/rule data set, paired with the `tz` reference
implementation for parsing and conversion.

## 2. Architecture

The database is partitioned into:

| File | Purpose |
|---|---|
| `africa`, `antarctica`, `asia`, `australasia`, `europe`, `northamerica`, `southamerica` | Per-continent zone definitions |
| `etcetera`, `backward`, `backzone` | Backwards-compatibility aliases |
| `factory` | Source for synthesized zones |
| `systemv` | Historical System V zone data |
| `leapseconds` | Leap second table (since 1972) |
| `leap-seconds.list` | Human-readable leap second list |
| `iso3166.tab` | Country codes for zones |
| `zone.tab`, `zone1970.tab`, `tzdata.zi` | Summary tables |
| `*.zi`, `Makefile` | Build-time source |
| `NEWS`, `CONTRIBUTING`, `README` | Maintainer-facing docs |

## 3. Zone Identifier Format

A canonical IANA zone identifier (TZ identifier) has the form
`Area/Location`:

- `Area` = one of `Africa`, `America`, `Antarctica`, `Asia`, `Atlantic`,
  `Australia`, `Europe`, `Indian`, `Pacific` (also `Etc` and `SystemV`).
- `Location` = `[_]?[[:alpha:]]+([_/][[:alpha:]]+)*` — alphanumeric, can
  include underscore and slash (e.g. `America/Argentina/Buenos_Aires`).
- Case-sensitive: `America/New_York` ≠ `america/new_york`.

### Examples

| TZ Identifier | UTC Offset (Standard) | DST Offset | Notes |
|---|---|---|---|
| `America/New_York` | -05:00 | -04:00 | Eastern Time |
| `America/Chicago` | -06:00 | -05:00 | Central Time |
| `America/Denver` | -07:00 | -06:00 | Mountain Time |
| `America/Los_Angeles` | -08:00 | -07:00 | Pacific Time |
| `America/Sao_Paulo` | -03:00 | (none) | Brazil abolished DST 2019 |
| `Europe/London` | +00:00 | +01:00 | BST |
| `Europe/Berlin` | +01:00 | +02:00 | CEST |
| `Europe/Moscow` | +03:00 | (none) | Russia abolished DST 2011 |
| `Asia/Tokyo` | +09:00 | (none) | JST, no DST since 1951 |
| `Asia/Kolkata` | +05:30 | (none) | India, no DST |
| `Asia/Kathmandu` | +05:45 | (none) | Nepal, fractional offset |
| `Australia/Sydney` | +10:00 | +11:00 | AEST/AEDT |
| `Pacific/Auckland` | +12:00 | +13:00 | NZST/NZDT |
| `UTC` | +00:00 | (none) | Default if no zone set |
| `Etc/UTC` | +00:00 | (none) | Equivalent to `UTC` |

## 4. Reference Profile Adopted by ORCHORDS

| Decision | Choice | Rationale |
|---|---|---|
| Identifier | Canonical IANA name | RFC 6557 (BCP 47 `-t` suffix uses the same) |
| Default | `UTC` | Server-side canonical |
| User-facing | IANA name shown alongside UTC offset | Avoid ambiguous abbreviations |
| Abbreviations | Lookup-only, never stored | `EST` is ambiguous (US vs Australia) |
| Historical lookup | Use IANA identifiers | `posixrules` or `posix/` style deprecated |
| Daylight Saving | Reflected in current rules | IANA tracks historical changes |
| Future rules | Use the latest release | ORCHORDS pins current release |
| Server time | Always UTC at the storage layer | Convert at edge per user zone |

## 5. Concrete Conversion Pattern

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+

# Server-side canonical storage
now_utc = datetime.now(timezone.utc)
print(now_utc)                       # 2026-09-04 14:30:00.123456+00:00

# Render in user zone
user_zone = ZoneInfo("America/New_York")
local = now_utc.astimezone(user_zone)
print(local)                         # 2026-09-04 10:30:00.123456-04:00

# DST handling is automatic
winter = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
summer = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
print(winter.astimezone(user_zone).strftime("%Z %z"))  # EST -0500
print(summer.astimezone(user_zone).strftime("%Z %z"))  # EDT -0400
```

## 6. Leap Seconds

IANA tzdata includes the leap-second table; conversions through a leap second
are non-momentary: `1972-06-30T23:59:60Z` is a valid one-second interval.
Most language runtimes (Python `datetime`, Java `Instant`, JavaScript `Date`,
Go `time`, Rust `chrono`) **do not** support leap seconds natively and treat
the leap second as a repeated second.

- For civil applications: ignore leap seconds (the IANA recommended approach for new code).
- For scientific/satellite applications: use TAI (International Atomic Time) and convert.
- For protocol-defined accuracy: pin to a UTC-SLS (smoothed) variant or accept ~1s error.

## 7. Common Pitfalls

| Pitfall | Correct | Rationale |
|---|---|---|
| Storing local time | Store UTC; convert at edge | DST rules change; historical conversions must be reproducible |
| Using `EST`/`PST` abbreviations | Use `America/New_York`, `America/Los_Angeles` | Abbreviations are ambiguous (ET = EST or EDT?) |
| Hardcoding offset for `Asia/Kolkata` | Use IANA zone | India has changed offset historically; future changes possible |
| Computing DST by date math | Look up via IANA | DST rules are political and change without warning |
| Using `timezone.utc` instead of `ZoneInfo("UTC")` | Either works | Stylistic; `Etc/UTC` and `UTC` are equivalent |
| Snapshotting tzdata | Refresh on every release (2-3x/year) | Stale data gives wrong answers during DST transitions |
| Trusting the OS bundled tzdata | Use a known-version pinned bundle (e.g., `tzdata` PyPI) | OS packages lag upstream by weeks/months |

## 8. Operating System Bundles

| OS | Package | Path | Refresh Cadence |
|---|---|---|---|
| Linux (glibc) | `tzdata` | `/usr/share/zoneinfo/` | Per distro; usually 1–2 weeks after upstream |
| macOS | Bundled with OS | `/usr/share/icu/icuc/zoneinfo.res` | Per OS release |
| Windows | `tzdata` NuGet package | `%TZDATA_RESOURCES%` | Microsoft ships via Windows Update |
| Alpine Linux | `tzdata` APK | `/usr/share/zoneinfo/` | Per release |
| Docker images | Varies; pin `tzdata` version | Inside the image | Per build |
| JVM | `tzdata.jar` from `java.time.zone` | Bundled in JRE | Per JRE release |

For production determinism, pin the version in CI; do not trust the running image.

## 9. Related Standards

- **ISO 8601:2019** — date/time format (carrier for tzdb-derived offsets).
- **RFC 3339** — Internet profile of ISO 8601.
- **RFC 6557** — BCP 47 extension `-t` for time-zone suffix (`en-US-u-tz-usnyc`).
- **RFC 9557** — suffix extensions for unknown offset and zone.
- **POSIX.1-2017 §8.3** — TZ environment variable syntax (`TZ=America/New_York`).
- **IETF tzdist** — proposals for distributing tzdb over HTTPS.

## 10. Version History

| Release | Date | Notable Changes |
|---|---|---|
| 2024a | 2024-02 | Kazakhstan unifies on UTC+5 |
| 2024b | 2024-09 | Palestine DST adjustments |
| 2025a | 2025-01 | Paraguay adopts year-round -03; various historic corrections |
| 2025b | 2025-06 | Antarctic stations updated |
| 2026a | 2026-03 | ORCHORDS current; numerous DST election cycles consolidated |
| 2026-09 | ORCHORDS reference card last reviewed |
