---
title: "Customer Cohort Analysis"
owner: "Customer Success Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Customer Cohort Analysis

## Purpose

Establish an accountable, evidence-based approach to defining, comparing, and acting on customer cohorts within the customer-success function. The objective is to surface patterns of attrition, adoption, and outcome attainment that inform investment, while preventing over-generalisation from cohorts whose composition is unstable or whose conclusions cannot survive a fairness review.

## Scope

This policy applies to any cohort analysis that groups customers for the purpose of customer-success decision-making — including adoption benchmarking, attrition curves, retention forecasting, intervention design, success-plan calibration, and reporting. It does not cover commercial or revenue cohorts whose sole purpose is pricing or finance; those are governed by commercial analytics policy. It does not cover one-off population snapshots whose conclusions are never reused.

## Requirements

- Every cohort MUST have a written operational definition: the inclusion event, the time-zero convention, the eligibility filter, the time window observed, and the population count at time zero.
- Time-zero conventions MUST be consistent across comparable analyses. Changing a time-zero definition MUST produce a documented migration note, an approval, and a period during which both conventions are reported side-by-side before the new convention becomes the default.
- Cohort populations MUST be reported with their size, the count of survivors at each observed interval, and the cumulative attrition at the relevant cut-off. Reports MUST disclose the interval length and the date the snapshot was taken.
- Cohort analysis MUST distinguish eligibility churn (a customer becomes ineligible by virtue of the cohort definition) from observed attrition (a customer is lost or disengaged). The two MUST NOT be combined without an explicit reconciliation that a non-technical reviewer can follow.
- Cohort analysis MUST be repeatable. Two independent analysts applying the same operational definition to the same underlying data MUST reach the same conclusions within a documented tolerance. Where the analysis depends on judgement, the judgement steps MUST be reviewed for consistency.
- Cohort analysis MUST include a fairness review. Where cohort outcomes vary materially by sub-population (region, industry, deployment model, customer size, or other relevant axis), the variation MUST be investigated and either explained, mitigated, or carried as an explicit caveat.
- Cohort analysis MUST be honest about censoring. Customers whose tenure is shorter than the observation window — for example, because they joined recently — MUST be reported as censored, not as evidence of attrition or retention.
- Cohort analysis MUST NOT be used to justify inaction for an individual customer on the basis of a population statistic. Population conclusions MUST inform intervention design but MUST NOT replace per-customer assessment.
- Cohort analysis MUST NOT be used to draw conclusions about customers who are not in the cohort. Generalisations from a cohort to the broader customer base MUST be supported by a documented comparison of the cohort to the excluded population.
- Small cohorts MUST be flagged. A cohort whose population at any observed interval falls below a documented minimum viable sample MUST NOT be used as the sole basis for a customer-facing decision without independent human review.
- Cohort analysis MUST record the data quality of its inputs. Where the underlying telemetry has known coverage gaps or calibration issues, the cohort analysis MUST disclose them.
- Cohort analysis MUST be stored in a system of record. The cohort definition, the population snapshot, the analysis method, and the conclusions drawn MUST be retrievable for the duration of the audit-retention window.
- Cohort analysis MUST be reviewed at a documented cadence. A cohort whose underlying population has materially changed MUST be re-baselined; continuing to apply the old conclusions to a different population is prohibited.

## Procedure

1. The analyst defines the cohort in writing, including time-zero convention, eligibility filter, observation window, and population count.
2. The analyst runs the cohort, records the survivor count at each interval, and identifies censoring.
3. A peer reviewer verifies the operational definition, the run, and the survivorship calculation.
4. The analyst produces the cohort report, including population size, attrition curve, censoring notes, sub-population variance, and limitations.
5. The cohort definition and the snapshot are stored in the system of record.
6. The cohort is reviewed at the documented cadence and re-baselined when the population changes materially.

## Stop conditions

- The cohort definition is no longer applicable to the current customer base.
- The data source has been decommissioned or replaced without a documented migration.
- The population at time zero falls below the documented minimum viable sample.
- The analysis cannot be reproduced by an independent analyst within a documented tolerance.
- The cohort has been retired by an explicit governance decision.

## Canonical sources

- ISO/IEC 27001:2022, Information security management — Requirements: https://www.iso.org/standard/27001
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ISO/IEC 5259-2:2024, Data quality — Part 2: Data quality measures: https://www.iso.org/standard/81088.html
- OECD, Data quality and statistics: https://www.oecd.org/digital/data-quality/
- U.S. Census Bureau, Statistical Quality Standards (public reference for cohort methodology norms): https://www.census.gov/about/policies/quality.html
- Eurostat, Statistical methodology (public reference for cohort analysis): https://ec.europa.eu/eurostat/web/quality/overview
- Customer Success Network, Cohort analytics (public guidance): https://www.customersuccessnetwork.com/
- ISO 20252:2019, Market, opinion and social research — Vocabulary and service requirements: https://www.iso.org/standard/73614.html