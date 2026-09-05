---
title: "Principles of Chaos Engineering Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Principles of Chaos Engineering; https://principlesofchaos.org/"
---

# Principles of Chaos Engineering Reference Card

## Scope

Reference card for the Principles of Chaos Engineering, the discipline of experimenting on a distributed system to build confidence in its capability to withstand turbulent conditions in production. Chaos engineering proceeds through four phases: define steady state, hypothesize, introduce perturbations, and try to disprove the hypothesis. Profiles that govern distributed-systems reliability should adopt the principles and bind to SLO Definition, Error Budget Policy, SRE Release Engineering, and the Google SRE Release Engineering reference.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | Principles of Chaos Engineering (Netflix et al.) |
| Companion artifacts | SLO Definition, Error Budget Policy, Google SRE Release Engineering |
| Source URL | https://principlesofchaos.org/ |

## Plan

1. Reference the Principles of Chaos Engineering in reliability-engineering policy and chaos-engineering practice documentation.
2. Define the steady state of the system in measurable terms (typically SLIs).
3. Hypothesize that the steady state will hold under a specific perturbation.
4. Introduce the perturbation (for example, kill a server, inject latency, partition the network).
5. Compare the observed steady state to the predicted steady state; try to disprove the hypothesis.
6. Use automated chaos experiments in production (with blast-radius controls) and in pre-production (with broader blast radius).
7. Adopt a chaos-engineering platform (for example, Chaos Mesh, Litmus, Gremlin) for repeatable, safe experiments.
8. Bind to SLO Definition for the steady-state reference.
9. Bind to Error Budget Policy for the reliability-budget consumption.
10. Bind to SRE Release Engineering for the deployment-pipeline integration.
11. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- Principles of Chaos Engineering (principlesofchaos.org).
- Steady-state measurements (typically the SLIs from the SLO Definition).
- Chaos-engineering platform configuration.
- Production-safety guardrails (blast-radius limits, automated rollback).
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats the Principles of Chaos Engineering as the canonical reference for proactive resilience validation. Profiles that govern distributed-systems reliability should define the steady state, hypothesize under perturbation, introduce perturbations in controlled blast-radius experiments, automate the experiments, and bind to the SLO Definition, Error Budget Policy, and SRE Release Engineering reference.

A profile that governs distributed-systems reliability without binding to the Principles of Chaos Engineering is non-conformant.

## Implementation Notes

- Steady-state measurements should be SLIs from the SLO Definition; chaos experiments should target SLO-relevant behavior.
- Production chaos experiments require blast-radius controls (for example, percentage of instances, time window, automated rollback).
- GameDays are a common format for chaos experiments: a scheduled event where teams run experiments against production.
- Chaos engineering complements, but does not replace, testing; chaos experiments target emergent behavior that unit and integration tests miss.
- The "blast-radius knob" is the most important control in a chaos-engineering platform; small experiments first.

## Companion Documents

- [SLO Definition](SERVICE_LEVEL_OBJECTIVE_DEFINITION.md)
- [Error Budget Policy](ERROR_BUDGET_POLICY.md)
- [Google SRE Release Engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md)
- [Google SRE Incident Management](GOOGLE_SRE_INCIDENT_MANAGEMENT.md)
- [NIST SP 800-84 Test, Training, and Exercise](NIST_SP_800_84_TEST_TRAINING_EXERCISE.md)
