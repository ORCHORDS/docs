---
title: "ML Training Run Reproducibility"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Training Run Reproducibility

## Scope

Defines the evidence and configuration capture required to reproduce an ML training run in ORCHORDS, so that any registered model can be audited, re-run, or recreated against the same inputs and produce comparable outputs.

## Identifier table

| Field | Value |
|---|---|
| Topic | Reproducibility evidence for ML training runs |
| Inputs | Code commit, dataset version, feature versions, hyperparameters, environment |
| Outputs | Training run manifest, reproducibility verification report |
| Audience | AI Platform, Audit, AIMS governance |
| Trigger | Every training run |
| Companion | ml-experiment-tracking-contract.md, ml-registry-promotion-gates.md |

## Plan

1. Capture the code commit identifier and the training entrypoint; reject runs without a pinned commit.
2. Capture dataset versions by identifier and hash; reject runs that reference a dataset without a current dataset card.
3. Capture feature versions by identifier and definition hash; reject runs that reference features with unresolved critical drift.
4. Capture the full hyperparameter set and any non-default environment variables.
5. Capture the environment specification: container image, compute type, library versions, and any GPU or accelerator configuration.
6. Sign the manifest by the training pipeline; store it alongside the model artifact.
7. Periodically re-run a sample of production training runs in a clean environment and compare key metrics within the documented tolerance.

## Inputs

- Code commit and entrypoint
- Dataset and feature version identifiers
- Hyperparameter and environment configuration

## ORCHORDS Profile

| Field | Validation |
|---|---|
| Code commit | Pinned and signed |
| Dataset versions | Match registered dataset cards |
| Feature versions | Match feature catalog; no unresolved critical drift |
| Hyperparameters | Full set captured; no opaque defaults |
| Environment | Container image digest and library versions recorded |

## Implementation Notes

- Treat the manifest as the canonical reproducibility contract; never accept a run with a partial manifest.
- Schedule reproducibility re-runs at least quarterly for production models.

## Companion Documents

- ml-experiment-tracking-contract.md
- ml-registry-promotion-gates.md
- ml-feature-store-schema-drift.md
