---
title: "ML Online Evaluation on Shadow Traffic"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Online Evaluation on Shadow Traffic

## Scope

Defines how ORCHORDS computes online evaluation metrics on shadow traffic so that candidate models can be compared against production models using real distribution inputs without serving responses to real consumers.

## Identifier table

| Field | Value |
|---|---|
| Topic | Online evaluation harness on shadow traffic |
| Inputs | Shadow responses, production responses, label sources, evaluator models |
| Outputs | Online evaluation report, comparison metrics, promotion evidence |
| Audience | AI Platform, Service Owners, AIMS governance |
| Trigger | Every candidate model in shadow evaluation |
| Companion | ml-shadow-deployment-strategy.md, ml-feature-freshness-sla.md |

## Plan

1. Configure the shadow evaluation harness to consume paired shadow and production responses.
2. Resolve labels using documented label sources: explicit user feedback, downstream outcome tracking, or evaluator models with documented confidence thresholds.
3. Compute per-class evaluation metrics with confidence intervals, plus per-segment metrics for protected attributes.
4. Detect statistically significant differences using the documented statistical test and significance threshold.
5. Publish the online evaluation report alongside the shadow deployment report.
6. Reject any candidate whose online evaluation does not match the shadow evaluation within the documented tolerance.
7. Archive the harness output for audit and replay.

## Inputs

- Shadow and production response streams
- Label source configuration
- Statistical test and significance threshold

## ORCHORDS Profile

| Setting | Value |
|---|---|
| Label source | Explicit feedback where available; downstream outcomes; evaluator model otherwise |
| Statistical test | Two-sided paired test at significance 0.05 |
| Confidence interval | 95 percent |
| Tolerance | Within 0.02 of shadow evaluation on aggregate metrics |

## Implementation Notes

- Treat evaluator models as versioned; document their lineage and limitations.
- Surface uncertainty in the report; do not promote on a single point estimate.

## Companion Documents

- ml-shadow-deployment-strategy.md
- ml-feature-freshness-sla.md
- ml-registry-promotion-gates.md
