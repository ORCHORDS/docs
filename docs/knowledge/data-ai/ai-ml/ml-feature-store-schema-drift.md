---
title: "ML Feature Store Schema Drift"
owner: "Data Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Feature Store Schema Drift

## Scope

Defines how ORCHORDS detects, communicates, and reconciles schema drift in feature stores so that downstream training and serving pipelines do not silently consume features with changed meaning, type, or distribution.

## Identifier table

| Field | Value |
|---|---|
| Topic | Schema drift detection and reconciliation in feature stores |
| Inputs | Feature definitions, observed types and distributions, consumer list |
| Outputs | Drift report, consumer notification, reconciliation ticket |
| Audience | Data Platform, AI Platform, Service Owners |
| Trigger | Any change in feature definition or observed schema |
| Companion | ml-training-run-reproducibility.md, ml-registry-promotion-gates.md |

## Plan

1. Maintain a documented feature catalog with feature identifier, owner, type, version, and intended semantic meaning.
2. Run periodic schema checks against the feature store and compare observed types and distributions with the catalog.
3. Classify drift by severity: critical (type change, breaking semantic change), high (distribution shift beyond threshold), medium (format change), low (cosmetic).
4. For every critical or high drift, identify consumers and notify each consumer owner with the drift ticket and proposed remediation.
5. Require consumer owners to either accept the drift with a documented plan, quarantine the feature, or roll back the producer change.
6. Block any new training run that consumes a feature with unresolved critical drift; serving may continue only with explicit override.
7. Re-run consumer health checks after reconciliation and record the outcome.

## Inputs

- Feature catalog with definitions and versions
- Observed feature store state
- Consumer inventory with owners

## ORCHORDS Profile

| Severity | Action |
|---|---|
| Critical | Block new training; serving override required |
| High | Notify consumers; quarantine or rollback within 24 hours |
| Medium | Notify consumers; remediate within 7 days |
| Low | Notify consumers; remediate within 30 days |

## Implementation Notes

- Treat feature semantics, not just types, as the source of truth; two features with the same type can still have critical drift.
- Make drift notifications idempotent; retries must not duplicate consumer notifications.

## Companion Documents

- ml-training-run-reproducibility.md
- ml-registry-promotion-gates.md
- ml-experiment-tracking-contract.md
