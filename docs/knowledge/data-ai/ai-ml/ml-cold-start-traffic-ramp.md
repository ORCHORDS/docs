---
title: "ML Cold Start Traffic Ramp"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# ML Cold Start Traffic Ramp

## Scope

Defines how ORCHORDS ramps traffic to a newly deployed ML model so that cold-start effects on latency, cache, and dependent services do not produce a sudden quality regression.

## Identifier table

| Field | Value |
|---|---|
| Topic | Traffic ramp procedure for cold ML model deployment |
| Inputs | Model identifier, deployment target, ramp schedule, SLO targets |
| Outputs | Ramp status, SLO compliance record, abort decision |
| Audience | AI Platform, Reliability Engineering, Service Owners |
| Trigger | Every new ML model deployment |
| Companion | ml-canary-rollback-criteria.md, ml-inference-budget-quota.md |

## Plan

1. Confirm the deployment target meets the documented prerequisites: capacity, health checks, and dependent service readiness.
2. Define a ramp schedule: 1 percent, 5 percent, 25 percent, 50 percent, 100 percent, with documented dwell time at each step.
3. At each step, compare SLO targets against observed metrics: latency, error rate, and any use-case-specific quality metric.
4. Abort the ramp on any SLO breach and roll back to the previous stable state; capture the abort reason.
5. Hold the ramp at the current step if metrics are within tolerance but trending toward breach; require explicit approval to continue.
6. Mark the deployment stable after the documented dwell time at 100 percent with no SLO breach.
7. Capture the ramp record with metrics, decisions, and final status for audit.

## Inputs

- Deployment target and prerequisites
- Ramp schedule and dwell times
- SLO targets per metric

## ORCHORDS Profile

| Step | Default dwell time |
|---|---|
| 1 percent | 15 minutes |
| 5 percent | 15 minutes |
| 25 percent | 30 minutes |
| 50 percent | 30 minutes |
| 100 percent | 60 minutes of stable observation |

## Implementation Notes

- Treat the ramp schedule as a release artifact; reject any deployment without an explicit schedule.
- Make abort decisions automatic on documented SLO breaches.

## Companion Documents

- ml-canary-rollback-criteria.md
- ml-inference-budget-quota.md
- ml-registry-promotion-gates.md
