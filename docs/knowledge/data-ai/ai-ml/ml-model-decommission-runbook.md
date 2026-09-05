---
title: "ML Model Decommission Runbook"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Model Decommission Runbook

## Scope

Defines how ORCHORDS decommissions models — deprecating, retiring, and archiving them — so that consumers are migrated safely, artifacts are preserved for audit, and no orphaned inference traffic continues after the documented sunset date.

## Identifier table

| Field | Value |
|---|---|
| Topic | Decommission procedure for ML models |
| Inputs | Model identifier, consumer list, sunset date, archive target |
| Outputs | Decommission plan, migration record, archive evidence |
| Audience | AI Platform, Service Owners, AIMS governance |
| Trigger | Model reaching end of life, performance regression, business deprecation |
| Companion | ml-registry-promotion-gates.md, ml-model-card-completeness.md |

## Plan

1. Confirm the decommission request with the model owner and AIMS governance; capture the rationale and the proposed sunset date.
2. Identify all consumers of the model — production traffic, batch jobs, ad hoc notebooks — and notify each consumer owner.
3. Define and publish a migration path for each consumer: replacement model, fallback policy, or explicit consumer retirement.
4. Block new consumer onboarding to the deprecated model from the announcement date forward.
5. Monitor consumer traffic weekly; confirm the traffic volume matches the migration plan.
6. At the sunset date, switch the model to a fail-closed serving behavior that returns a typed error; preserve any required telemetry for the documented retention period.
7. Move the artifact to archive with the model card, dataset card references, evaluation report, and reproducibility manifest; record the archive identifier.

## Inputs

- Model identifier and registry stage
- Consumer inventory with owners
- Sunset date and migration plan

## ORCHORDS Profile

| Phase | Duration |
|---|---|
| Announcement to deprecation | At least 30 days before sunset |
| Deprecation to sunset | At least 30 days; longer for high-blast-radius models |
| Archive retention | Minimum 7 years for regulated use cases; program default otherwise |

## Implementation Notes

- Treat decommission as a migration program, not a single event; consumer owners need notice and support.
- Preserve the artifact and its lineage; do not delete them.

## Companion Documents

- ml-registry-promotion-gates.md
- ml-model-card-completeness.md
- ml-fine-tune-data-governance.md
