---
title: "EU AI Act — Annex III High-Risk Use Cases Version Guide"
standard: EU Regulation 2024/1689 Annex III
publisher: European Parliament and Council
category: reference
subcategory: ai-governance
canonical_url: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689
status: approved
classification: public
audience: ai-governance, legal, product, security-engineering
last-reviewed: 2026-09-05
review-cycle: 12 months
next-review: 2027-09-05
---

## Scope

Annex III of the EU AI Act enumerates the use cases classified as high-risk.
Providers and deployers of AI systems in these categories must implement
conformity assessment, risk management, data governance, transparency,
human oversight, accuracy/robustness/cybersecurity, and post-market
monitoring obligations before placing the system on the EU market.

This guide captures the Annex III categories, the obligations that flow from
classification, and how ORCHORDS profiles Annex III in product intake and
AI risk registers.

## Identifier Table

| Field | Value |
| --- | --- |
| Instrument | Regulation (EU) 2024/1689 |
| Article | Annex III |
| Title | High-risk AI systems referred to in Article 6(2) |
| Entry into force | 1 August 2024 |
| Applicability | Phased from 2 February 2025; full applicability August 2026 |
| Companion | Article 5 (prohibited), Article 6 (classification), Article 9–15 (obligations), Annex IV (technical documentation) |

## Plan

ORCHORDS screens each AI use case against Annex III categories before
authorising deployment and proceeds as follows:

1. Maintain a use case inventory tagged against each Annex III clause (1–8).
2. Run a high-risk classification decision per use case with documented
   evidence.
3. For high-risk classifications, generate Annex IV technical documentation
   and apply Article 9–15 obligations.
4. Hold conformity assessment before EU market release and on any
   substantial modification.
5. Run post-market monitoring per Article 72 and report serious incidents
   per Article 73.

## Inputs

- AI use case intake form and system description.
- Stakeholder and fundamental rights impact assessment output.
- Training, validation, and test data provenance records.
- Provider/deployer roles and responsibilities matrix.
- Existing AIMS risk register and conformity reports.

## ORCHORDS Profile Table

| Annex III category | Examples under ORCHORDS scope | Default classification |
| --- | --- | --- |
| 1. Biometrics | Identity verification, emotion recognition | High-risk if used in law enforcement or workplace surveillance |
| 2. Critical infrastructure | Safety control in energy, water, traffic | High-risk |
| 3. Education and vocational training | Assessment scoring, admissions | High-risk if affects access |
| 4. Employment | CV screening, evaluation | High-risk |
| 5. Essential services | Credit scoring, insurance pricing, emergency dispatch | High-risk |
| 6. Law enforcement | Predictive policing, evidence reliability | High-risk |
| 7. Migration, asylum, border | Risk assessment, identity verification | High-risk |
| 8. Administration of justice and democracy | Judicial assistance, election influence | High-risk |

## Implementation Notes

- Classification is determined per use case, not per AI model. A general
  model can drive both high-risk and non-high-risk deployments.
- Where a use case is borderline, ORCHORDS defaults to high-risk and
  discharges the obligations unless a documented justification is approved.
- Fundamental rights impact assessment (Article 27) is mandatory for deployers
  of high-risk systems; ORCHORDS records this in the deployment record.
- Substantial modification triggers a new conformity assessment and updated
  technical documentation.

## Companion Documents

- EU AI Act Reference Card
- EU AI Act — Article 5 Prohibited Practices Reference Card
- EU AI Act — GPAI Obligations Reference Card
- ISO/IEC 42001:2023 Reference Card
- ISO/IEC 42005 Reference Card
- NIST AI 100-1 Reference Card
