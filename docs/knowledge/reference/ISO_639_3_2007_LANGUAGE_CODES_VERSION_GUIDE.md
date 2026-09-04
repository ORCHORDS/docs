---
title: "ISO 639-3:2007 Language Codes Version Guide"
standard: "ISO 639-3"
standard_edition: "2007-07 (1st edition)"
publisher: "International Organization for Standardization (ISO)"
maintenance_agency: "SIL International (Registration Authority)"
category: "reference"
subcategory: "language-codes"
canonical_url: "https://iso639-3.sil.org/"
status: "approved"
classification: "public"
audience: "engineers"
last_reviewed: "2026-09-04"
---

# ISO 639-3:2007 Language Codes Version Guide

## 1. Purpose

ISO 639-3 provides a three-letter code for every known natural language,
including extinct, ancient, and constructed languages. It supersedes and
extends ISO 639-1 (2-letter codes for major languages) and ISO 639-2
(3-letter codes for terminology and bibliographic use). This guide pins
ORCHORDS adoption of ISO 639-3:2007 for fine-grained language identification
when ISO 639-1's 184 codes are insufficient.

## 2. Relationship to Other ISO 639 Parts

| Part | Codes | Length | Scope |
|---|---|---|---|
| ISO 639-1 | 184 | 2-letter | Major languages (Bashkir `ba`, Basque `eu`, etc.) |
| ISO 639-2 | ~485 | 3-letter | Terminology and bibliographic (Bashkir `bak`, Basque `baq`/`eus`) |
| ISO 639-3 | ~7,900 | 3-letter | All natural languages (Bashkir `bak`, Basque `eus`) |
| ISO 639-4 | n/a | n/a | Guidelines for the implementation of ISO 639 |
| ISO 639-5 | ~2,000 | 3-letter | Language families and groups |
| ISO 639-6 | (deprecated) | 4-letter | Local variants |
| ISO 639-7 | (proposed) | — | Macrolanguages |

## 3. Code Format and Properties

```
code        = 3 lowercase letters   (eng, spa, fra, deu, cmn, yue, ...)
range       = a..z
case        = lowercase canonical; uppercase per BCP 47 normalization
scope       = individual | macrolanguage | collection | private-use | retired
type        = living | extinct | ancient | constructed | special
```

## 4. Reference Profile Adopted by ORCHORDS

| Decision | Choice | Rationale |
|---|---|---|
| Default | ISO 639-1 (2-letter) | Compatibility with HTTP `Accept-Language` and BCP 47 short tags |
| Fallback | ISO 639-3 (3-letter) | For languages not in ISO 639-1 |
| Case | Lowercase canonical | ISO 639-3 §3 |
| Macrolanguages | Map to individual children when known | `cmn` (Mandarin) → `cmn-Hans`/etc. |
| Retired codes | Reject | Do not assign new content to retired codes |
| Private-use | Accept `qaa`..`qtz` | ISO 639-3 §4 |
| Special | `und` (undetermined), `mul` (multiple), `zxx` (no linguistic content) | Allowed |

## 5. Worked Examples

| Language | ISO 639-3 | ISO 639-1 | Notes |
|---|---|---|---|
| English | eng | en | |
| Mandarin Chinese | cmn | zh | Macro-language: `zh` |
| Cantonese | yue | (none) | ISO 639-3 only |
| Arabic | ara | ar | Macro-language; children include `arb`, `arz`, `ary` |
| Egyptian Arabic | arz | (none) | |
| Yiddish | yid | yi | ISO 639-2 has `yid` |
| Esperanto | epo | eo | Constructed |
| Klingon | tlh | (none) | Constructed; ISO 639-3 special case |
| Latin | lat | la | Ancient |
| Old English | ang | (none) | Historical |
| Navajo | nav | nv | |
| Ojibwe | oji | oj | Macro-language; children: `ojb`, `ojc`, `ojg`, etc. |

## 6. Macrolanguage Handling

A macrolanguage groups closely-related individual languages. Examples:

- **Arabic** (`arb` Modern Standard, `ary` Moroccan, `arz` Egyptian, `acw` Hijazi, `apd` Sudanese, ...)
- **Chinese** (`cmn` Mandarin, `yue` Cantonese, `wuu` Wu, `hsn` Xiang, `nan` Min, ...)
- **Malay** (`zsm` Standard, `ind` Indonesian, `zlm` Colloquial, ...)

For NLP and translation, use the individual language code; for fallback
language detection, use the macrolanguage.

## 7. Implementation Notes

- Authoritative source: SIL International `iso639-3.sil.org`.
- Tables distributed as TSV: `iso-639-3.tab`, `iso-639-3-macrolanguages.tab`, `iso-639-3-name-index.tab`.
- Updates 2–3 times per year; ORCHORDS syncs weekly.
- ISO 639-3 codes are valid BCP 47 language subtags; pair with script/region per BCP 47.

## 8. Common Pitfalls

| Pitfall | Correct | Rationale |
|---|---|---|
| `ch` for Chinese | `zh` (ISO 639-1) or `cmn` (ISO 639-3 Mandarin) | `ch` is not assigned |
| `sh` for Serbo-Croatian | `sr` (Serbian), `hr` (Croatian), or `hbs` (Serbo-Croatian macrolanguage) | `sh` deprecated |
| `iw` for Hebrew | `he` (ISO 639-1) | `iw` was the legacy code from RFC 1766 |
| `in` for Indonesian | `id` | `in` deprecated; Indonesian uses `id` |
| Using 2-letter for low-resource languages | Use ISO 639-3 (e.g. `haw` Hawaiian, `mi` Māori) | 2-letter doesn't cover ~7,700 languages |

## 9. Versioning and Source of Truth

- SIL International is the ISO 639-3 Registration Authority.
- Change requests are reviewed by the ISO 639-3 Registration Authority and posted to the public mailing list.
- Code statuses: `Active`, `Retired`.

## 10. Related Standards

- **ISO 639-1** — short 2-letter codes.
- **BCP 47** — language tags for protocols.
- **ISO 15924** — script codes.
- **Unicode CLDR** — locale repository that derives language codes from ISO 639-3.
- **Glottolog** — linguistic reference for language relationships; often paired with ISO 639-3.

## 11. Validation

ORCHORDS rejects unknown ISO 639-3 codes with HTTP 400 `invalid_language_code`.
Retired codes trigger a 410 `language_code_retired` if the request specifies
`?allow_retired=false` (default).

## 12. Version History

| Edition | Year | Notes |
|---|---|---|
| 1st | 2007 | ISO 639-3:2007 |
| Updates | annual | New codes for recently identified languages; some retirements |
| 2026-09 | ORCHORDS reference card last reviewed |
