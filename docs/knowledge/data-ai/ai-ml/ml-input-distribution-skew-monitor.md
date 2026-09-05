---
title: "ML Input Distribution Skew Monitor"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Input Distribution Skew Monitor

## Scope

Defines how ORCHORDS monitors the input distribution of online inference against the training and reference distributions, so that distribution skew is detected, alerted, and remediated before it degrades model quality.

## Identifier table

| Field | Value |
|---|---|
| Topic | Input distribution skew monitoring for ML inference |
| Inputs | Online input stream, training reference distribution, skew metrics |
| Outputs | Skew report, alert, remediation actions |
| Audience | AI Platform, Service Owners, AIMS governance |
| Trigger | Continuous |
| Companion | ml-feature-freshness-sla.md, ml-canary-rollback-criteria.md |

## Plan

1. Capture the training and reference input distributions at training time and store them as the reference distribution.
2. Sample the online input stream at a documented rate and compute distribution statistics.
3. Compute skew metrics per feature: population stability index, Jensen-Shannon divergence, and any use-case-specific statistic.
4. Compare against documented skew thresholds; alert on threshold breach and page on sustained breach.
5. Investigate any skew alert; correlate with upstream data sources, traffic sources, and feature freshness.
6. Open a remediation ticket on confirmed skew; route through the canary rollback path if skew affects quality.
7. Refresh the reference distribution on documented retraining or context change.

## Inputs

- Reference distribution per feature
- Online sampled input stream
- Skew metric thresholds

## ORCHORDS Profile

| Metric | Threshold |
|---|---|
| Population stability index | 0.10 or higher triggers alert |
| Jensen-Shannon divergence | 0.05 or higher triggers alert |
| Sustained breach | 30 minutes triggers page |

## Implementation Notes

- Treat the reference distribution as a release artifact; refresh only with documented retraining.
- Surface skew metrics on the model health dashboard alongside quality metrics.

## Companion Documents

- ml-feature-freshness-sla.md
- ml-canary-rollback-criteria.md
- ml-registry-promotion-gates.md
