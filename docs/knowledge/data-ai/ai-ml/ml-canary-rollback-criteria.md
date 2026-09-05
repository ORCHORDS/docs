---
title: "ML Canary Rollback Criteria"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Canary Rollback Criteria

## Scope

Defines the rollback criteria that trigger automatic or manual rollback of a canary ML model, so that regressions in quality, safety, cost, or latency are contained before they reach the full production population.

## Identifier table

| Field | Value |
|---|---|
| Topic | Automatic and manual rollback criteria for canary ML models |
| Inputs | Canary metrics, production metrics, baseline metrics, rollback thresholds |
| Outputs | Rollback decision, rollback action, post-incident review |
| Audience | AI Platform, Reliability Engineering, Service Owners |
| Trigger | Continuous during canary |
| Companion | ml-shadow-deployment-strategy.md, ml-registry-promotion-gates.md |

## Plan

1. Define per-metric rollback thresholds: quality (faithfulness drop), safety (toxicity, refusal rate), latency (p95 increase), cost (per-task increase), and reliability (error rate, circuit breaker activity).
2. Compare canary metrics against the documented baseline; trigger rollback on any threshold breach sustained for the documented evaluation window.
3. Allow manual rollback by Service Owner or on-call at any time during the canary.
4. Execute rollback automatically: shift traffic back to the previous production model, freeze the canary, and notify stakeholders.
5. Capture rollback telemetry: metric that triggered, magnitude, duration, and downstream effects.
6. Open a post-incident review for any rollback that triggered within the documented noise window.
7. Update thresholds and noise window based on observed canary history.

## Inputs

- Canary and baseline metrics streams
- Rollback thresholds and noise window per metric
- Rollback authority list

## ORCHORDS Profile

| Metric | Default rollback threshold |
|---|---|
| Faithfulness drop | 0.05 absolute from baseline |
| Toxicity or refusal rate increase | 0.05 absolute from baseline |
| p95 latency increase | 25 percent from baseline |
| Cost per task increase | 25 percent from baseline |
| Error rate | 2x baseline sustained 5 minutes |

## Implementation Notes

- Treat rollback as a first-class operation; the rollback path must be tested before each canary.
- Make the rollback decision auditable; record the metric, the threshold, and the actor.

## Companion Documents

- ml-shadow-deployment-strategy.md
- ml-registry-promotion-gates.md
- ml-input-distribution-skew-monitor.md
