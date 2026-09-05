---
title: "Google SRE Release Engineering Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Google SRE Book Chapter 8 (Release Engineering); https://sre.google/sre-book/release-engineering/"
---

# Google SRE Release Engineering Reference Card

## Scope

Reference card for Google SRE release engineering practices: build systems, source-control workflows, automated testing, hermetic builds, canary analysis, and rollback mechanisms. Release engineering treats the deployment pipeline as a software system in its own right, with the same engineering rigor as the application. Profiles that govern production deployments should adopt SRE release engineering practices and bind to the SLO Definition, Error Budget Policy, and SLSA / NIST SP 800-218 supply-chain references.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | Google SRE Book Chapter 8 (Release Engineering) |
| Companion artifacts | SLSA, NIST SP 800-218, NIST SP 800-218A, NIST SP 800-161, SLO Definition, Error Budget Policy |
| Source URL | https://sre.google/sre-book/release-engineering/ |

## Plan

1. Reference SRE release engineering in deployment-pipeline documentation and SDLC policy.
2. Adopt hermetic builds: builds depend only on declared inputs and produce reproducible artifacts.
3. Adopt the source-control workflow: trunk-based development with short-lived branches, code review, automated checks.
4. Adopt automated testing at multiple levels: unit, integration, end-to-end, performance, security.
5. Adopt staged rollouts: canary, progressive delivery, automated rollback on error-rate increase.
6. Adopt the concept of "build engineer" or release-engineering ownership of the pipeline.
7. Bind to SLSA for the supply-chain integrity treatment.
8. Bind to NIST SP 800-218 and SP 800-218A for the SDLC treatment.
9. Bind to SLO Definition and Error Budget Policy for the deployment-gate treatment.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- Google SRE Book Chapter 8.
- Build system configuration (Bazel, Buck, or equivalent).
- Source-control workflow (Git, Phabricator, or equivalent).
- Deployment pipeline with staged rollouts and automated rollback.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats SRE release engineering as the canonical reference for production deployment practices. Profiles that govern production deployments should adopt hermetic builds, trunk-based development with code review, multi-level automated testing, staged rollouts with automated rollback, and bind to SLSA, NIST SP 800-218/218A, and the SLO/Error Budget policy.

A profile that governs production deployments without binding to SRE release engineering is non-conformant.

## Implementation Notes

- Hermetic builds use containerization or sandboxing to isolate build dependencies; this prevents non-reproducible builds.
- Trunk-based development reduces merge conflicts and improves release predictability; long-lived branches are non-conformant.
- Canary analysis compares metrics (error rate, latency, business KPIs) between canary and baseline populations; automated rollback should fire on significant regression.
- The release engineer role is distinct from the application engineer; the release engineer owns the pipeline, not the application.
- Configuration management (feature flags, configuration as code) is part of release engineering and should be versioned and audited.

## Companion Documents

- [Google SRE Incident Management](GOOGLE_SRE_INCIDENT_MANAGEMENT.md)
- [SLO Definition](SERVICE_LEVEL_OBJECTIVE_DEFINITION.md)
- [Error Budget Policy](ERROR_BUDGET_POLICY.md)
- [Supply Chain Levels for Software Artifacts (SLSA)](SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [NIST SSDF SP 800-218](NIST_SSDF_SP_800_218.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
