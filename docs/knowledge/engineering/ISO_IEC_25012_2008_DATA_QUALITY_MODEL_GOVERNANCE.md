# ISO/IEC 25012:2008 Data Quality Model Governance

## Purpose

ISO/IEC 25012:2008, *Software engineering — Software product Quality Requirements and Evaluation (SQuaRE) — Data quality model*, defines data quality characteristics for data held in a computer system, organized into inherent and system-dependent categories — 15 characteristics from syntactic accuracy and completeness to availability and portability.

Data-producing and data-consuming systems should apply the 25012 model so that data quality requirements are stated against defined characteristics with measurable criteria rather than as the ambient ambition "clean data".

## Scope

Applies to the studio's systems that produce, transform, store, or consume data at scale. Covers data quality characteristic selection, requirement expression, and measurement orientation. Does not cover product quality (25010) or the evaluation process (25040).

## Workflow

1. Select applicable 25012 characteristics per dataset: inherent characteristics (syntactic accuracy, semantic accuracy, completeness, consistency, credibility, currency, timeliness) and system-dependent ones (availability, portability, recoverability, confidentiality, efficiency, precision, reliability, traceability, understandability) — record which apply and why.
2. Express data quality requirements as characteristic plus measurable criterion: "completeness: mandatory-field population ≥ 99.5% per record batch" — not "data must be complete".
3. Assign each data quality requirement to a measurement: how, where in the pipeline (at ingestion, in storage, at consumption), and with what threshold and response.
4. Distinguish inherent from system-dependent defects: a completeness gap at ingestion (inherent) and an availability failure in storage (system-dependent) have different owners and remediations; the model keeps them separate.
5. Instrument the pipeline: quality checks run as pipeline stages with results recorded per batch or per period, producing a data quality trend, not one-off audits.
6. Bind quality findings to remediation: failed thresholds open correction tasks with owners — data quality debt tracked like technical debt.
7. Revisit characteristic selection as data use evolves: new consumers (analytics, ML training) add characteristics (traceability, semantic accuracy) that batch operations did not need.

## Controls and evidence

- Characteristic applicability record per dataset.
- Data quality requirements with measurable criteria and thresholds.
- Pipeline instrumentation configuration and per-batch quality results.
- Data quality trend reporting.
- Remediation task records with owners and closure evidence.

## Validation

- Sample one dataset: confirm its requirements state characteristics with measurable criteria and thresholds.
- Confirm the pipeline quality checks run per batch with results recorded.
- Confirm failed thresholds in the period opened remediation tasks that closed.

## Failure correction

- **Requirement without measurable criterion** → restate against the characteristic with a threshold; unmeasurable requirements are removed from the register.
- **Quality check gaps (characteristic not instrumented)** → add the check at the pipeline stage where the defect class is detectable.
- **Remediation backlog growing unbounded** → prioritize by downstream impact; chronic defects without remediation are accepted risk only by explicit decision.

## Limitations

25012 defines the model; measurement methods and tooling are outside it. ML-specific data concerns (distribution shift, label quality) partially map to currency/completeness/semantic accuracy but carry their own evolving practices. The 2008 edition predates large-scale ML data practice — apply the model as a framework, supplement with domain practice.

## Scope note

This article is part of the engineering leaf. Cross-reference: `ISO_IEC_25010_2011_SOFTWARE_PRODUCT_QUALITY_MODEL.md`, `ISO_IEC_15939_2017_MEASUREMENT_PROCESS_GOVERNANCE.md`, and `W3C_DCAT_3_DATA_CATALOG_TEMPLATE_GOVERNANCE.md` (templates leaf).

## Canonical sources

- ISO/IEC 25012:2008 — SQuaRE — Data quality model: https://www.iso.org/obp/ui/#iso:std:iso-iec:25012:ed-1
- ISO/IEC 25024 — SQuaRE — Measurement of data quality: https://www.iso.org/obp/ui/#iso:std:iso-iec:25024
- ISO/IEC 25010:2011 — SQuaRE — System and software quality models: https://www.iso.org/obp/ui/#iso:std:iso-iec:25010:ed-1
- ISO 8000 — Data quality series: https://www.iso.org/obp/ui/
- DAMA International — Data Management Body of Knowledge (DMBOK): https://www.dama.org/
