---
title: "IETF BCP 47 Language Tags Version Guide"
standard: "BCP 47"
standard_status: "Best Current Practice"
publisher: "Internet Engineering Task Force (IETF)"
primary_documents:
  - "RFC 5646 (Tags for Identifying Languages)"
  - "RFC 4647 (Matching Language Tags)"
  - "RFC 4646 (Tags for the Identification of Languages — historical)"
category: "reference"
subcategory: "locale-identification"
canonical_url: "https://datatracker.ietf.org/doc/bcp/bcp47/"
status: "approved"
classification: "public"
audience: "engineers"
last_reviewed: "2026-09-04"
---

# IETF BCP 47 Language Tags Version Guide

## 1. Purpose

BCP 47 is the IETF Best Current Practice for identifying human languages in
protocols and data formats. It supersedes RFC 1766 and the older `Accept-Language`
HTTP usage from RFC 2616. This guide pins ORCHORDS adoption of BCP 47 for
language tags in user profiles, content metadata, and translation workflows.

## 2. Tag Structure (RFC 5646 §2.1)

```
language-tag   = langtag / privateuse / grandfathered
langtag        = language ["-" script] ["-" region] *("-" variant) *("-" extension) ["-" privateuse]
language       = 2*3ALPHA            ; shortest ISO 639 code
script         = 4ALPHA              ; ISO 15924
region         = 2ALPHA / 3DIGIT     ; ISO 3166-1 alpha-2 / UN M.49
variant        = 5*8alphanum / (DIGIT 3alphanum)
extension      = singleton 1*("-" (2*8alphanum))
singleton      = DIGIT / [A-WY-Z]    ; single letter or digit except X
```

## 3. Reference Profile Adopted by ORCHORDS

| Component | Decision | Source |
|---|---|---|
| Language | ISO 639-1 (2-letter) preferred, ISO 639-3 (3-letter) fallback | RFC 5646 §2.2.1 |
| Script | ISO 15924 alpha-4 | RFC 5646 §2.2.3 |
| Region | ISO 3166-1 alpha-2 | RFC 5646 §2.2.4 |
| Variant | IANA Subtag Registry `Variant` subtag | RFC 5646 §2.2.5 |
| Extensions | Lowercase singleton prefix | RFC 5646 §2.2.6 |
| Private-use | `-x-` prefix | RFC 5646 §2.2.7 |
| Case | All subtags lowercase; region uppercase by convention | RFC 5646 §2.1.1 |
| Length cap | No hard limit but recommend ≤ 35 chars | RFC 5646 §4.5 |

## 4. Concrete Examples

```
en                          (English, no region)
en-US                       (English, United States)
en-GB                       (English, United Kingdom)
zh-Hans                     (Chinese, Simplified script)
zh-Hant-HK                  (Chinese, Traditional, Hong Kong)
sr-Latn-RS                  (Serbian, Latin, Serbia)
sl-nedis                    (Slovenian, Natisone dialect variant)
de-DE-1996                  (German, Germany, 1996 orthography variant)
und                         (undetermined — RFC 5646 §4.1)
x-private                   (private-use only)
```

## 5. Matching (RFC 4647)

ORCHORDS supports two matching strategies; defaults to **lookup** for static
content negotiation and **filtering** for user-preference lists:

- **Lookup** — return the longest matching tag from the user's preference list that the resource supports. Single best match.
- **Filtering** — return all supported tags that are within range of a preference tag. Subset.

## 6. Forbidden Constructs

- Mixed case in subtags: `En-us` — must be `en-US`.
- Region as numeric 3-digit when 2-letter exists: prefer `DE` over `276`.
- Two-letter language not in ISO 639-1 unless grandfathered.
- Extension singletons other than `[0-9A-WY-Za-wy-z]`; `x` is reserved for private-use.

## 7. Versioning

The IANA Subtag Registry is the authoritative source; it is updated continuously
and the record types are: `language`, `extlang`, `script`, `region`, `variant`,
`grandfathered`, `redundant`, `language-collection`. ORCHORDS validators cache
the registry and refresh on a weekly cron.

## 8. Validation

Recommended parser is ICU `ULocale.forLanguageTag()` (Java/.NET via ICU4C),
or `Intl.Locale` in JavaScript engines that support ECMA-402. Both reject
malformed tags and normalize case.

## 9. Related Standards

- **ISO 639-1 / 639-2 / 639-3** — language code sets.
- **ISO 15924** — script codes.
- **ISO 3166-1** — country/region codes.
- **UN M.49** — numeric region codes (3-digit).
- **CLDR** — Unicode Common Locale Data Repository, often paired with BCP 47 for formatting.

## 10. Version History

| Year | Action |
|---|---|
| 1995 | RFC 1766 (Tags for the Identification of Languages) |
| 1997 | RFC 2070 (HTML i18n) |
| 2002 | RFC 3066 (replaced RFC 1766) |
| 2006 | RFC 4646 / RFC 4647 — modern matching framework |
| 2009 | RFC 5646 — current; replaced RFC 4646/3066 |
| 2026-09 | ORCHORDS reference card last reviewed |
