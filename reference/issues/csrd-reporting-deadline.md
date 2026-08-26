# csrd-reporting-deadline

**Issue:** EU CSRD reporting — when to start, what to track
**Date:** 2026-08-09
**Status:** documented (compliance checklist)

## Symptom
Your company meets the CSRD threshold. The reporting deadline
is 12 months away. You have no data. The first year requires
retroactive data from FY-1. You're late.

## Root cause
CSRD (Corporate Sustainability Reporting Directive) requires
disclosure of ESG (environmental, social, governance) metrics
aligned with ESRS (European Sustainability Reporting Standards).
The scope is large:
- **E1-E5:** Environmental (climate, pollution, water, biodiversity,
  circular economy)
- **S1-S4:** Social (workforce, value chain, communities,
  consumers)
- **G1:** Governance (business conduct, risk management)

**Source:** CSRD text:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2464

> "Large undertakings ... shall report in accordance with
> Directive 2013/34/EU ... on sustainability matters."

## When does it apply?

| Entity | First reporting year | Deadline |
|---|---|---|
| Public-interest entities > 500 employees | FY 2024 | 2025 |
| Other large undertakings | FY 2025 | 2026 |
| Listed SMEs | FY 2026 (optional 2027) | 2027 (optional 2028) |
| Non-EU parent companies with EU activity | FY 2028 | 2029 |

For a consumer-platform with > 250 employees OR > €50M revenue
OR > €25M balance sheet, CSRD applies.

## What to track

### Environmental (E1)
- **GHG emissions:** Scope 1 (direct), Scope 2 (purchased energy),
  Scope 3 (value chain)
- **Energy use:** renewable vs non-renewable
- **Climate risks:** physical (flood, wildfire) + transition
  (carbon pricing)
- **Carbon credits:** purchased offsets, avoided emissions

### Social (S1)
- **Workforce:** headcount, FTE, diversity (gender, age,
  nationality)
- **Pay gap:** gender pay gap, CEO-to-median ratio
- **Health & safety:** incidents, fatalities
- **Training:** hours per employee, types of training
- **Collective bargaining:** % covered

### Governance (G1)
- **Board composition:** independence, diversity, skills
- **Ethics:** corruption incidents, anti-corruption training
- **Data protection:** GDPR violations, fines
- **Lobbying:** lobbying spend, memberships
- **Suppliers:** code of conduct compliance, audits

## Fix
For a tech platform:

### Start now if you haven't
The data for FY-1 (the year BEFORE reporting) is needed. If you
start tracking now, you'll have FY+1 data when the deadline hits.

### Use the data you have
- **GHG Scope 2** = electricity bills
- **Workforce headcount** = payroll records
- **Diversity** = HR self-ID (voluntary)
- **Data protection violations** = your DPO incident log

### Data you DON'T have (start collecting)
- **GHG Scope 3** = full value chain emissions (data center
  suppliers, employee commute, customer device energy)
- **Climate risk** = physical asset risk exposure
- **Pay gap** = detailed compensation analysis

### Tools
- **Watershed** or **Persefoni** for GHG accounting
- **Workiva** for the actual CSRD report (XBRL format)
- **Spreadsheets** for the first year (a CSRD report is
  ~50-200 data points; spreadsheets are fine)

### Audit
CSRD reports must be **assured** (audited) by an independent
third party. Limited assurance for the first year; reasonable
assurance from year 3.

## Verification
- **Test:** All 50-200 data points are collected for FY
- **Live:** The CSRD report is published in XBRL format on
  the company's website
- **Audit:** Annual third-party assurance

## Gotchas
- **The first year is "limited assurance"** (lower bar). Use
  the time to build the data infrastructure.
- **Materiality assessment is required.** You don't report
  everything — you report what's material to your business.
  Document the assessment.
- **XBRL is the format.** The CSRD report is machine-readable.
  Use a tool that outputs XBRL (Workiva, KPMG's Climate IQ,
  etc.).
- **Non-EU companies with EU activity are now in scope** (CSRD
  Article 40a). If you have EU users, you may be in scope
  even if you're US-based.
- **The penalty for non-compliance varies by country** but
  typically includes fines and reputational damage.
- **CSRD ≠ ESG ratings.** CSRD is regulatory disclosure. ESG
  ratings (MSCI, Sustainalytics) are voluntary. Don't conflate.

## Related
- `gdpr-article-17-erasure.md` (related EU regulation)
- `compliance/region-matrix.md` (where CSRD applies)
- CSRD text: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2464
- ESRS standards: https://www.efrag.org/sites/default/files/website/media/2024-08-08/ESRS%20Delegated%20Act%20-%20Annex%20I%20-%20Final%20draft.pdf
