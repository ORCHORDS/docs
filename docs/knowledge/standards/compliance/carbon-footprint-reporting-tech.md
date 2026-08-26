# carbon-footprint-reporting-tech

**Issue:** Calculating and reporting Scope 1, 2, and 3 GHG emissions for technology companies
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tech companies face increasing pressure from regulators (CSRD, SEC climate rule), investors, and enterprise customers to report carbon footprints with Scope 3 transparency. Software and cloud infrastructure are major emission sources.

## Pattern / Solution
GHG Protocol scopes:
- Scope 1: Direct emissions from owned sources (office heating/cooling with gas, company vehicles)
- Scope 2: Indirect emissions from purchased electricity (data center power, office electricity)
  - Market-based: use renewable energy certificates (RECs) or PPAs
  - Location-based: grid average emission factor
- Scope 3: All other indirect emissions — typically 70-90% of tech company total

Tech-specific Scope 3 categories:
```
Category 1 (Purchased goods): hardware procurement emissions (use supplier data or industry factors)
Category 2 (Capital goods): server and network equipment manufacturing
Category 3 (Fuel and energy related): transmission and distribution losses
Category 5 (Waste): office waste, data center waste
Category 6 (Business travel): flights, hotels (use booking platform data)
Category 7 (Employee commuting and WFH): commute surveys + WFH energy
Category 11 (Use of sold products): customer energy consumption from your SaaS/software
Category 12 (End of life): hardware disposal
```

Cloud infrastructure emissions:
- AWS: Customer Carbon Footprint Tool (CCFT) — monthly reports by service and region
- GCP: Google Cloud Carbon Footprint — similar
- Azure: Emissions Impact Dashboard
- Use these as primary data source for cloud Scope 2 and 3 Category 1

Reporting cadence: annual GHG inventory; third-party verification recommended; align with financial year.

Science-based targets (SBTi): commit to net-zero aligned target; validate with SBTi for credibility.

## Gotchas
- Cloud providers report market-based Scope 2 (after RECs) — this may undercount actual grid emissions
- Scope 3 Category 11 (use of sold products) requires customer energy data — model if not available
- Do not net removals against emissions without SBTi or CSRD-aligned methodology
- Employee WFH energy is often omitted but required under CSRD

## Related
- `esg-reporting-frameworks.md`
- `csrd-reporting.md`
