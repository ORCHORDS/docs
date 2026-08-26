# esg-reporting-frameworks

**Issue:** Navigating ESG reporting frameworks: GRI, SASB, TCFD, ISSB, and EU CSRD
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Multiple ESG reporting frameworks exist with different scopes and audiences. CSRD (EU) and ISSB (IFRS S1/S2) are converging toward mandatory reporting, while GRI and SASB remain voluntary best practices.

## Pattern / Solution
Framework comparison:

| Framework | Scope | Audience | Mandatory? |
|-----------|-------|----------|-----------|
| GRI Standards | Multi-stakeholder impact | Broad public | Voluntary |
| SASB | Sector-specific financially material ESG | Investors | Voluntary |
| TCFD | Climate-related financial risks/opportunities | Investors | Voluntary (basis for ISSB/CSRD) |
| ISSB IFRS S1/S2 | Sustainability-related financial disclosures | Investors | Mandatory in many jurisdictions 2024+ |
| CSRD (EU) | Double materiality (impact + financial) | Broad public + investors | Mandatory for large EU companies |

CSRD (EU) — most comprehensive:
- Applies to: large EU companies (>500 employees, listed); non-EU companies with >EUR 150M EU net turnover
- Use European Sustainability Reporting Standards (ESRS)
- Double materiality: disclose both financial risks FROM sustainability AND impact ON environment/society
- Third-party assurance required
- First reports for FY2024 (for largest companies); phased rollout through 2028

Key metrics tech companies typically report:
- Environment: Scope 1/2/3 GHG emissions, energy consumption, % renewable energy, data center PUE
- Social: employee diversity (gender, ethnicity by level), pay equity analysis, training hours, safety metrics
- Governance: board diversity, ethics violations, cyber incidents, data privacy compliance

Scope 3 for tech companies:
- Category 1: Purchased goods and services (hardware manufacturing)
- Category 11: Use of sold products (customer energy consumption from your software/hardware)
- Category 12: End-of-life treatment of sold products

## Gotchas
- CSRD requires ESRS — not GRI/SASB/TCFD directly, though cross-references exist
- Scope 3 data quality is challenging — use industry average factors initially, improve over time
- Assurance provider must be qualified; limited assurance initially, reasonable assurance by 2028
- Value chain data requirements under CSRD are extensive — supply chain engagement needed

## Related
- `csrd-reporting.md`
- `carbon-footprint-reporting-tech.md`
- `modern-slavery-act-compliance.md`
