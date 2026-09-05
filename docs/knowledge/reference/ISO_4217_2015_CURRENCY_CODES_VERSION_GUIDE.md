---
title: "ISO 4217:2015 Currency Codes Version Guide"
standard: "ISO 4217"
standard_edition: "2015-08 (8th edition)"
publisher: "International Organization for Standardization (ISO)"
maintenance_agency: "SIX Group Ltd on behalf of ISO 3166/MA"
category: "reference"
subcategory: "currency-codes"
canonical_url: "https://www.iso.org/iso-4217-currency-codes.html"
status: "approved"
classification: "public"
audience: "engineers"
last_reviewed: "2026-09-04"
---

# ISO 4217:2015 Currency Codes Version Guide

## 1. Purpose

ISO 4217 defines alpha-3 and numeric codes for currencies used in international
commerce. Codes are maintained by the SIX Group on behalf of the ISO 3166
Maintenance Agency. This guide pins the ORCHORDS profile of ISO 4217:2015
(8th edition) as the source of truth for currency identifiers in payments,
pricing, and FX-aware accounting.

## 2. Code Format

```
alpha-3  = 3 uppercase letters   (USD, EUR, JPY, GBP, CHF)
numeric  = 3 digits              (840, 978, 392, 826, 756)
minor    = 2 digits              (exponent for minor unit; e.g. USD = 2, JPY = 0)
```

## 3. Reference Profile Adopted by ORCHORDS

| Decision | Choice | Rationale |
|---|---|---|
| Primary | Alpha-3 | Human-readable, ubiquitous |
| Storage | Alpha-3 + numeric + minor unit exponent | Triple canonical form |
| Case | Uppercase | ISO 4217 §4 |
| Minor units | Always carry `MinorUnit` exponent | Avoid `100` vs `1000` confusion (JPY vs KWD) |
| Historical codes | Retain for 10 years after retirement | Migration grace |
| Metal codes | Reject (XAU gold, XAG silver, etc.) unless explicitly supported | Metal codes are out of scope for payment processing |
| Supranational | Accept `EUR`, `XOF`, `XAF`, `XCD` etc. | All ISO 4217 registered |
| Test codes | Reject `XTS` (reserved for testing) | Never appear in production |

## 4. Worked Examples

| Currency | Alpha-3 | Numeric | Minor Unit | Symbol |
|---|---|---|---|---|
| US Dollar | USD | 840 | 2 | $ |
| Euro | EUR | 978 | 2 | € |
| Japanese Yen | JPY | 392 | 0 | ¥ |
| British Pound Sterling | GBP | 826 | 2 | £ |
| Swiss Franc | CHF | 756 | 2 | CHF |
| Kuwaiti Dinar | KWD | 414 | 3 | د.ك |
| Bitcoin (no ISO 4217) | — | — | — | ₿ |
| ISO 4217 list (2015) | 178 active | 178 numeric | — | — |

## 5. Money Storage Pattern

```sql
CREATE TABLE monetary_amount (
  amount_minor  BIGINT NOT NULL,           -- integer in minor units
  currency_code CHAR(3) NOT NULL,         -- ISO 4217 alpha-3
  scale         SMALLINT NOT NULL,        -- minor unit exponent (cache)
  CONSTRAINT chk_currency_iso CHECK (currency_code ~ '^[A-Z]{3}$')
);
```

Avoid `DECIMAL(19,4)` for cross-currency math — different currencies have
different exponents and an implicit scale can corrupt FX conversions.

## 6. Common Pitfalls

| Pitfall | Correct | Rationale |
|---|---|---|
| `RMB` for Chinese yuan | `CNY` (offshore) or `CNH` (onshore) | `RMB` is the colloquial name; not an ISO 4217 code |
| Symbol-only display | Always emit alpha-3 for APIs | `$` is ambiguous (USD, AUD, CAD, HKD, etc.) |
| Floating-point math | Use integer minor units + BigDecimal/BigInt | IEEE-754 cannot represent 0.10 exactly |
| Hardcoded exponent | Store `MinorUnit` per currency | JPY = 0, USD = 2, KWD = 3 |
| Code change tracking | Subscribe to ISO 4217 newsletter | Codes added/retired (e.g. `BYR` → `BYN` in 2016) |

## 7. Notable Historical Transitions

| Date | Old | New | Notes |
|---|---|---|---|
| 2002-01-01 | `EUR` introduced | 12 legacy codes retired | ADM, FRF, DEM, ITL, ESP, etc. |
| 2007-07-01 | `CYP` → `EUR` | Cyprus Euro adoption | |
| 2016-07-01 | `BYR` → `BYN` | Belarus ruble redenomination | 10000 BYR = 1 BYN |
| 2023-01-01 | `ZWL` suspended | ZWL→ZIG revaluation | Reserve Bank of Zimbabwe |
| 2025-01-01 | — | New codes per newsletter | Subscribe for current |

## 8. Versioning and Source of Truth

- ISO 4217 Maintenance Agency: SIX Group Ltd (Zurich).
- The list is updated monthly; the official XML and CSV are available to subscribers.
- The European Central Bank publishes daily reference rates against EUR.
- OANDA, OpenExchangeRates, and ECB publish periodic rate snapshots for FX.

## 9. Related Standards

- **ISO 3166-1** — country codes for currency's issuing jurisdiction.
- **ISO 20022** — financial messaging schema; uses ISO 4217 currency codes.
- **SWIFT MT103** — legacy wire format; ISO 4217 currency codes required.
- **SEPA** — Single Euro Payments Area; `EUR` only.
- **PCI-DSS** — when storing card-related data; not directly tied to ISO 4217 but often co-stored.

## 10. Validation

ORCHORDS rejects unknown alpha-3 codes with HTTP 400 `invalid_currency_code`.
The numeric code is not a primary identifier; we cross-reference but accept
either form on input.

## 11. Version History

| Edition | Year | Notes |
|---|---|---|
| 1st | 1978 | ISO 4217:1978 |
| 2nd | 1987 | ISO 4217:1987 |
| 3rd | 1990 | ISO 4217:1990 |
| 4th | 1995 | ISO 4217:1995 |
| 5th | 2001 | ISO 4217:2001 |
| 6th | 2008 | ISO 4217:2008 |
| 7th | 2013 | ISO 4217:2013 |
| 8th | 2015 | ISO 4217:2015 — current |
| 2026-09 | ORCHORDS reference card last reviewed |
