---
title: "ML Shadow Deployment Strategy"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Shadow Deployment Strategy

## Scope

Defines how ORCHORDS uses shadow deployments to validate candidate models against production traffic without serving responses to real consumers, so that regressions in quality, latency, and cost are detected before promotion.

## Identifier table

| Field | Value |
|---|---|
| Topic | Shadow deployment pattern for ML model validation |
| Inputs | Candidate model artifact, traffic mirror configuration, comparison harness |
| Outputs | Shadow evaluation report, promotion recommendation |
| Audience | AI Platform, Service Owners, AIMS governance |
| Trigger | Every candidate promotion request to candidate or production |
| Companion | ml-online-evaluation-shadow-traffic.md, ml-canary-rollback-criteria.md |

## Plan

1. Confirm the candidate model passes the candidate stage gates and is eligible for shadow evaluation.
2. Mirror a documented fraction of production traffic to the candidate model using the traffic mirror service.
3. Disable any side effects on the shadow path: no writes to production systems, no outbound communications, no cache pollution.
4. Capture shadow responses alongside the production response with timestamps and correlation identifier.
5. Compute comparison metrics: agreement rate, faithfulness, latency, cost, and any quality-specific metric for the use case.
6. Compare against the documented promotion thresholds; block promotion if any threshold is violated.
7. Publish the shadow evaluation report and feed findings back into the candidate owner.

## Inputs

- Candidate model identifier and revision
- Traffic mirror configuration
- Comparison metrics and thresholds

## ORCHORDS Profile

| Setting | Value |
|---|---|
| Mirror fraction | Configurable; default 5 percent for general agents, 1 percent for high-traffic |
| Comparison window | At least 7 days of mirror traffic |
| Side-effect prevention | Hard isolation: shadow path has no production credentials |
| Promotion thresholds | Documented per use case; block on any violation |

## Implementation Notes

- Treat the mirror as ephemeral; do not persist shadow responses beyond the comparison window unless the comparison harness requires it.
- Make shadow traffic isolation enforceable at the network and credential layers; never rely on application-level checks alone.

## Companion Documents

- ml-online-evaluation-shadow-traffic.md
- ml-canary-rollback-criteria.md
- ml-registry-promotion-gates.md
