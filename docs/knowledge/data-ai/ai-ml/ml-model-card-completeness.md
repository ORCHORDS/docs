---
title: "ML Model Card Completeness"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Model Card Completeness

## Scope

Defines the required sections, validation rules, and review cadence for ML model cards published by ORCHORDS, so consumers can read a model card and understand what the model is for, what it is not for, and how it was trained.

## Identifier table

| Field | Value |
|---|---|
| Topic | Completeness requirements for ML model cards |
| Inputs | Training metadata, evaluation results, intended use, governance review |
| Outputs | Validated model card with required sections and reviewers |
| Audience | AI Platform, Service Owners, AIMS governance |
| Trigger | Every new model registration, every major revision |
| Companion | ml-dataset-card-provenance.md, ml-registry-promotion-gates.md |

## Plan

1. Define required sections: model identifier, version, training summary, intended use, out-of-scope use, training data summary, evaluation metrics, fairness and bias summary, limitations, monitoring plan, owner, and review date.
2. Validate at registration time that all required sections are present and non-empty; reject registration otherwise.
3. Validate at promotion time that the evaluation metrics, fairness summary, and limitations are not stale relative to the current revision.
4. Require sign-off from the model owner and from the AIMS reviewer before the card is published to consumers.
5. Validate that the card links to the dataset card, evaluation report, and registry entry by identifier.
6. Detect stale cards by comparing the card review date against the model revision date; flag any card older than the documented threshold.
7. Publish completeness metrics to governance so that gaps are visible at the program level.

## Inputs

- Training run metadata
- Evaluation and fairness report
- Intended and out-of-scope use statement
- Owner and reviewer attestations

## ORCHORDS Profile

| Section | Validation |
|---|---|
| Model identifier and version | Non-empty, matches registry identifier |
| Intended use | Non-empty, with at least one explicit exclusion |
| Training data summary | Links to dataset card; non-empty |
| Evaluation metrics | Non-empty, references evaluation report identifier |
| Fairness and bias summary | Required for any production model; risk-accept otherwise |
| Monitoring plan | Defines at least one drift or quality signal |
| Owner and review date | Owner present; review date within 90 days |

## Implementation Notes

- Treat the model card as a release artifact; it is regenerated on every revision and signed by the model registry.
- Reject any registration whose card links to a dataset card marked stale or withdrawn.

## Companion Documents

- ml-dataset-card-provenance.md
- ml-registry-promotion-gates.md
- ml-training-run-reproducibility.md
