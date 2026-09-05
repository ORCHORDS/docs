---
title: "ML Model Card CI Validation"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Model Card CI Validation

## Scope

Defines how ORCHORDS validates the model card in the continuous integration pipeline, so that every model registration includes a complete card that meets documented standards and is signed before promotion.

## Identifier table

| Field | Value |
|---|---|
| Topic | CI validation rules for ML model cards |
| Inputs | Model card draft, schema version, registry identifier, evaluation report |
| Outputs | Validation report, signed card, promotion decision |
| Audience | AI Platform, Model Owners, AIMS governance |
| Trigger | Every model card draft or revision in the CI pipeline |
| Companion | ml-model-card-completeness.md, ml-registry-promotion-gates.md |

## Plan

1. Define the card schema: required sections, allowed values, and validation rules.
2. Run the schema validator on every model card draft in the CI pipeline.
3. Validate cross-references: dataset card present and current, evaluation report present, registry identifier matches the artifact.
4. Validate that the fairness and bias summary is present and current for any production model.
5. Reject any draft that fails validation; surface the failing rule and the remediation path to the author.
6. Sign the validated card with the build provenance attestation and bind it to the model registry entry.
7. Archive the validation report alongside the card for audit.

## Inputs

- Model card draft in CI
- Schema version and validation rules
- Evaluation and fairness reports

## ORCHORDS Profile

| Validation rule | Severity |
|---|---|
| Required sections present | Error |
| Cross-references valid | Error |
| Fairness summary current | Error for production models |
| Review date within 90 days | Warning |
| Owner attestation present | Error |

## Implementation Notes

- Treat the validator as a release gate; block CI on any error.
- Version the schema and bump the version on any breaking change.

## Companion Documents

- ml-model-card-completeness.md
- ml-registry-promotion-gates.md
- ml-experiment-tracking-contract.md
