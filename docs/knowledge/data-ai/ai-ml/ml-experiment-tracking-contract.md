---
title: "ML Experiment Tracking Contract"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Experiment Tracking Contract

## Scope

Defines the schema and review cadence for experiment tracking in ORCHORDS so that every experiment — successful, failed, or aborted — produces comparable, queryable evidence that supports governance, audit, and model promotion.

## Identifier table

| Field | Value |
|---|---|
| Topic | Experiment tracking schema and review cadence |
| Inputs | Experiment metadata, code reference, parameters, metrics, artifacts |
| Outputs | Experiment record with documented fields and lineage |
| Audience | AI Platform, AIMS governance, Model Owners |
| Trigger | Every experiment, regardless of outcome |
| Companion | ml-training-run-reproducibility.md, ml-registry-promotion-gates.md |

## Plan

1. Define the experiment record schema: identifier, owner, code reference, dataset reference, parameters, metrics, status, environment, timestamps, and review notes.
2. Require every experiment to be recorded at start, with status updates as it progresses; require a final record at completion regardless of outcome.
3. Validate that the code reference is a pinned commit and that the dataset reference is a registered dataset card.
4. Validate that metrics are recorded with the same units and definitions across experiments; reject ambiguous or unitless metrics.
5. Link artifacts such as model checkpoints, plots, and logs to the experiment record; never store them without a parent record.
6. Detect experiments that are open or stale beyond the documented threshold and notify owners.
7. Publish queryable experiment records to the experiment tracker so that promotion decisions can cite them directly.

## Inputs

- Code commit, dataset reference, parameters, metrics, environment
- Experiment owner and reviewer

## ORCHORDS Profile

| Field | Validation |
|---|---|
| Identifier and owner | Non-empty; owner active in IAM |
| Code reference | Pinned commit; matches training manifest |
| Dataset reference | Registered dataset card; not withdrawn |
| Metrics | Documented unit; comparable across experiments |
| Status | Final status recorded for 100 percent of started experiments |

## Implementation Notes

- Treat failure and aborted outcomes as first-class; do not delete experiment records because the model did not promote.
- Make the experiment tracker the source of truth for promotion decisions; promotion tickets cite the experiment identifier.

## Companion Documents

- ml-training-run-reproducibility.md
- ml-registry-promotion-gates.md
- ml-model-card-completeness.md
