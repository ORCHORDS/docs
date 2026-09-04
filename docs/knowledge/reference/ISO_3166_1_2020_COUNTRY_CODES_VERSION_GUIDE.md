---
title: "ISO 3166-1:2020 Country Codes Version Guide"
standard: "ISO 3166-1"
standard_edition: "2020-08 (5th edition)"
publisher: "International Organization for Standardization (ISO)"
maintenance_agency: "ISO 3166 Maintenance Agency (ISO 3166/MA) — formerly CLDR-derivable"
category: "reference"
subcategory: "country-region-codes"
canonical_url: "https://www.iso.org/iso-3166-country-codes.html"
status: "approved"
classification: "public"
audience: "engineers"
last_reviewed: "2026-09-04"
---

# ISO 3166-1:2020 Country Codes Version Guide

## 1. Purpose

ISO 3166-1 defines codes for the names of countries, dependent territories,
and special areas of geographical interest. The standard is published in three
parts: alpha-2 (two-letter), alpha-3 (three-letter), and numeric (three-digit).
This guide pins the ORCHORDS profile of ISO 3166-1:2020 for geographic
addressing, currency routing, language fallback, and tax/VAT calculation.

## 2. Code Sets

| Code Set | Length | Use Case | Example |
|---|---|---|---|
| Alpha-2 | 2 letters | Country code top-level domains (ccTLD), BCP 47 region subtags | `US`, `DE`, `JP` |
| Alpha-3 | 3 letters | ISO 4217 currency country component, airline/IATA-style contexts | `USA`, `DEU`, `JPN` |
| Numeric | 3 digits | UN M.49-aligned numeric codes for stats, customs, BCP 47 region | `840`, `276`, `392` |

## 3. Reference Profile Adopted by ORCHORDS

| Decision | Choice | Rationale |
|---|---|---|
| Primary | Alpha-2 | Shortest; ubiquitous in ccTLD, BCP 47 |
| Storage | Alpha-2 + Alpha-3 (no numeric unless required) | API consumers typically need both |
| Case | Uppercase | ISO 3166-1 §5 |
| Reserved codes | Use alpha-2 reserved range for XK (Kosovo) caveat | XK not in ISO 3166-1 but widely deployed; allow as `XK` only with explicit comment |
| User-assigned | Reserved alpha-2 codes (`AA`, `QM–QZ`, `XA–XZ`, `ZZ`) | EU/UN reserved for internal use |
| Deletion handling | When a country is removed from ISO 3166-1, retain as historical with `status: retired` for 5 years | Migration grace |

## 4. Worked Examples

| Country | Alpha-2 | Alpha-3 | Numeric | ccTLD | Currency (ISO 4217) |
|---|---|---|---|---|---|
| United States | US | USA | 840 | .us | USD |
| Germany | DE | DEU | 276 | .de | EUR |
| Japan | JP | JPN | 392 | .jp | JPY |
| United Kingdom | GB | GBR | 826 | .uk | GBP |
| Switzerland | CH | CHE | 756 | .ch | CHF |
| Brazil | BR | BRA | 076 | .br | BRL |
| South Africa | ZA | ZAF | 710 | .za | ZAR |

## 5. Implementation Notes

- Use the official ISO 3166-1 online browsing platform for current codes; do not snapshot old copies.
- When ISO 3166-1 and UN M.49 diverge (rare; ~10 codes historically), document both.
- For territories that are *part of* another country (e.g., Faroe Islands `FO`, Greenland `GL`), use the territory code; for the parent country, use its code.
- For Antarctica, use `AQ`; for the European Union (a supranational entity, not a country), use `EU`.

## 6. Common Pitfalls

| Pitfall | Correct | Rationale |
|---|---|---|
| `UK` for United Kingdom | `GB` | `UK` is reserved (no official assignment); `GB` is the ISO 3166-1 alpha-2 |
| `KS` for Kosovo | `XK` (with explicit comment) or omit | ISO 3166-1 does not list Kosovo; `XK` is a de-facto user assignment |
| `TP` for East Timor | `TL` | ISO 3166-1 alpha-2 changed from `TP` to `TL` in 2002 |
| `ZR` for Congo (DRC) | `CD` | Changed from `ZR` to `CD` in 1997 |

## 7. Versioning and Source of Truth

- The ISO 3166 Maintenance Agency (ISO 3166/MA) is the only authority for additions, deletions, and changes.
- ISO 3166-1 newsletter updates are issued periodically (multiple times per year).
- The Unicode CLDR derives its `territory` codes from ISO 3166-1; CLDR is a convenient mirror but not authoritative.

## 8. Validation

ORCHORDS stores a normalized table of (alpha-2, alpha-3, numeric, name) tuples
fetched weekly. Unknown codes produce HTTP 400 with `invalid_country_code`.

## 9. Related Standards

- **ISO 3166-2** — subdivision codes (state, province, region); required for sub-national addressing.
- **ISO 4217** — currency codes; alpha-3, paired with ISO 3166-1 for country context.
- **UN M.49** — statistical region codes; numeric ISO 3166-1 alpha is a subset.
- **ITU-T E.164** — international telephone numbering; country calling codes are 1–3 digits.
- **BCP 47 §2.2.4** — region subtag uses ISO 3166-1 alpha-2 or UN M.49 numeric.

## 10. Version History

| Edition | Year | Notes |
|---|---|---|
| 1st | 1997 | ISO 3166-1:1997 |
| 2nd | 2006 | ISO 3166-1:2006 |
| 3rd | 2013 | ISO 3166-1:2013 |
| 4th | 2019 | ISO 3166-1:2019 |
| 5th | 2020 | ISO 3166-1:2020 — current |
| 2026-09 | ORCHORDS reference card last reviewed |
