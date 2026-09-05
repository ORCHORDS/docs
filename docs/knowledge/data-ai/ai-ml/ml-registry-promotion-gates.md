---
title: "ML Registry Promotion Gates"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Registry Promotion Gates

## Scope

Defines the gates that must pass before a model artifact can be promoted between registry stages — dev, staging, candidate, production — in ORCHORDS, so that promotion is auditable, reproducible, and reversible.

## Identifier table

| Field | Value |
|---|---|
| Topic | Promotion gates between model registry stages |
| Inputs | Model artifact, manifest, evaluation report, fairness report, approvals |
| Outputs | Promotion record, stage transition, audit log |
| Audience | AI Platform, AIMS governance, Model Owners |
| Trigger | Every promotion request |
| Companion | ml-experiment-tracking-contract.md, ml-model-card-completeness.md |

## Plan

1. Define the registry stages: dev, staging, candidate, production, deprecated, retired.
2. Define gates per stage transition: reproducibility evidence present, evaluation report meets documented thresholds, fairness report meets documented thresholds, model card complete, owner and AIMS approver attested, no unresolved security findings.
3. Validate that the promotion request includes the source stage identifier, the target stage, and the artifact identifier.
4. Block any promotion that fails a gate; surface the failing gate and the remediation path to the requester.
5. On success, record the promotion event with approvers, timestamps, and gate results; make the record immutable.
6. Validate that the target stage is empty for the model identifier, or that the existing entry is being explicitly superseded; reject ambiguous promotions.
7. Allow automated rollback from production to candidate when a documented regression signal triggers, with on-call approval.

## Inputs

- Model artifact identifier and stage
- Manifest, evaluation report, fairness report
- Owner and AIMS attestations

## ORCHORDS Profile

| Transition | Required gates |
|---|---|
| dev to staging | Reproducibility manifest present; basic evaluation reported |
| staging to candidate | Evaluation thresholds met; fairness report present |
| candidate to production | AIMS approver attested; monitoring plan in place; model card complete |
| production to deprecated | Owner attested; sunset date documented |
| deprecated to retired | All consumers removed; artifact archived |

## Implementation Notes

- Treat promotion records as immutable; corrections require a new promotion event, not edits.
- Reject any promotion that tries to skip a stage.

## Companion Documents

- ml-experiment-tracking-contract.md
- ml-model-card-completeness.md
- ml-model-decommission-runbook.md
