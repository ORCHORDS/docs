---
title: "Error Budget Policy Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Google SRE Book Chapter 3 (Eliminating Toil) and Chapter 4 (Service Level Objectives); https://sre.google/sre-book/eliminating-toil/"
---

# Error Budget Policy Reference Card

## Scope

Reference card for the error budget policy, the mechanism that translates an SLO into a concrete reliability target. The error budget is 1 minus the SLO; if a service spends its budget, the next reliability-or-feature decision is biased toward reliability. Profiles that govern reliability should adopt the error budget policy, integrate it with deployment gates, and bind to the SLO Definition, SRE Incident Management, and SRE Release Engineering references.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | Google SRE Book Chapter 3 (Eliminating Toil) and Chapter 4 (Service Level Objectives) |
| Companion artifacts | SLO Definition, Google SRE Incident Management, Google SRE Release Engineering |
| Source URL | https://sre.google/sre-book/eliminating-toil/ |

## Plan

1. Reference the error budget policy in reliability engineering policy and SRE practice documentation.
2. Define the SLO first; the error budget is derived from the SLO.
3. Set the budget burn-rate alert thresholds (for example, 2% budget burned in 1 hour, 5% in 6 hours).
4. Define the policy when budget is exhausted: freeze non-critical deployments, escalate to the reliability steering committee, prioritize reliability work.
5. Reset the budget on a defined cadence (typically 28 days or monthly).
6. Track the budget burn rate in real time and surface it to the service team.
7. Bind to SLO Definition for the underlying SLO.
8. Bind to SRE Incident Management for incident-response alignment.
9. Bind to SRE Release Engineering for deployment-gate alignment.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- SLO Definition for the service.
- Real-time availability and latency telemetry.
- Deployment pipeline with budget-aware gates.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats the error budget as the canonical mechanism for balancing reliability and feature velocity. Profiles that govern reliability should derive the budget from the SLO, define budget burn-rate alert thresholds, define the policy when budget is exhausted, reset the budget on a defined cadence, and bind to the SLO Definition, SRE Incident Management, and SRE Release Engineering references.

A profile that defines an SLO without an error budget policy is non-conformant.

## Implementation Notes

- Multi-window burn-rate alerts (for example, 1-hour and 6-hour windows) reduce false positives while preserving fast detection.
- Budget exhaustion does not mean stop all work; it means bias the next decision toward reliability.
- The error budget should be visible to product and engineering leadership, not just the SRE team.
- Budget policy should be tested by deliberate failure injection (for example, chaos engineering) to validate the response.

## Companion Documents

- [SLO Definition](SERVICE_LEVEL_OBJECTIVE_DEFINITION.md)
- [Google SRE Incident Management](GOOGLE_SRE_INCIDENT_MANAGEMENT.md)
- [Google SRE Release Engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md)
- [Principles of Chaos Engineering](PRINCIPLES_OF_CHAOS_ENGINEERING.md)
- [Blameless Post-Incident Review](BLAMELESS_POST_INCIDENT_REVIEW.md)
