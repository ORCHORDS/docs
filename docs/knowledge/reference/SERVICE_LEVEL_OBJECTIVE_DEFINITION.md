---
title: "Service Level Objective (SLO) Definition Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Google SRE Book Chapter 4 (Service Level Objectives); https://sre.google/sre-book/service-level-objectives/"
---

# Service Level Objective (SLO) Definition Reference Card

## Scope

Reference card for Service Level Objectives (SLOs), the reliability target for a service expressed as a numerical objective over a window. SLOs are derived from Service Level Indicators (SLIs) and inform Service Level Agreements (SLAs). Profiles that govern service reliability should adopt SLOs, derive them from user-impacting measurements, and bind to the Error Budget Policy and SRE Incident Management / Release Engineering references.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | Google SRE Book Chapter 4 (Service Level Objectives) |
| Companion artifacts | Error Budget Policy, Google SRE Incident Management, Google SRE Release Engineering |
| Source URL | https://sre.google/sre-book/service-level-objectives/ |

## Plan

1. Reference SLO Definition in reliability engineering policy and service documentation.
2. Define SLIs first: the user-impacting measurements (for example, request success rate, request latency).
3. Define SLOs from SLIs: the target value over a window (for example, 99.9% success rate over 28 days).
4. Avoid SLAs in the SLO; SLAs are contractual, SLOs are internal. SLOs should be stricter than SLAs.
5. Document the rationale for the SLO target; the rationale drives the error budget policy.
6. Adopt a small number of SLOs per service; many SLOs dilute focus.
7. Bind to Error Budget Policy for the reliability-velocity trade-off.
8. Bind to SRE Incident Management for incident-response alignment.
9. Bind to SRE Release Engineering for deployment-gate alignment.
10. Re-evaluate SLOs at least annually.
11. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- Google SRE Book Chapter 4.
- Service telemetry: request success rate, latency, availability.
- User-impact analysis: what user actions are affected by which SLI regressions.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats the SLO Definition as the canonical reference for reliability targets. Profiles that govern service reliability should define SLIs first, derive SLOs from SLIs, document the rationale for the SLO target, adopt a small number of SLOs per service, and bind to the Error Budget Policy and SRE references.

A profile that governs service reliability without binding to the SLO Definition is non-conformant.

## Implementation Notes

- SLIs should be measured from the user's perspective, not from internal infrastructure; user-side telemetry is preferred.
- A common SLO is 99.9% (three nines) for user-facing services, but the right SLO depends on user impact and cost.
- Window length matters: 28-day and 30-day windows are common for SLOs because they balance statistical significance and operational cadence.
- SLO targets should be reviewed after major incidents; a recurring near-miss is a signal that the SLO is too loose.
- The SLO must be communicated to product and engineering leadership; reliability is a product feature.

## Companion Documents

- [Error Budget Policy](ERROR_BUDGET_POLICY.md)
- [Google SRE Incident Management](GOOGLE_SRE_INCIDENT_MANAGEMENT.md)
- [Google SRE Release Engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md)
- [Blameless Post-Incident Review](BLAMELESS_POST_INCIDENT_REVIEW.md)
