# SRE Release Coordination and Error Budget Governance

## Purpose

Site Reliability Engineering (SRE) practices use error budgets to balance reliability against and innovation. The error budget defines the maximum acceptable unreliability for a service (e.g., 99.9% availability over a quarter allows for ~43 minutes of downtime per quarter). When the error budget is consumed, releases are paused until the budget resets or until reliability improves. This article governs the application of release coordination and error budget practices so they operate with discipline and are integrated with the change management process.

## Scope

The article applies to organizations practicing SRE or SRE-adjacent operations. Within this knowledge base, the article covers the error budget definition, the measurement of reliability against the budget, the release coordination decisions when the budget is consumed, the policy that defines how the budget interacts with release velocity, and the documentation of the budget state. It does not cover the substantive engineering of the service or the SLO definition process.

## Workflow

1. Define the service's SLOs (Service Level Objectives) and the resulting error budget. The SLO defines the target reliability; the error budget is the inverse (the allowed unreliability).
2. Measure reliability continuously against the SLO. Maintain the budget consumption record.
3. Integrate the budget state into the release coordination process:
   - When budget remains: releases proceed per the normal change process.
   - When budget is approaching exhaustion: prioritization shifts to reliability work; releases may be paused to recover budget.
   - When budget is exhausted: releases of features are paused until reliability is restored or the budget resets.
4. Document the budget state and the release decisions in a visible record so the team and stakeholders can see the position.
5. Review the SLO and the budget on a planned cadence and on service changes. Adjust the SLO only with documented justification.

## Controls and evidence

Budget controls include the SLO definition, the reliability records, the budget consumption, the release decisions tied to budget state, and the review records. The budget state should be visible (dashboard) and the release decisions should be auditable.

## Validation

Validation should confirm the SLOs are defined, the measurement is accurate, the budget consumption is current, the release decisions reflect the budget state, and the review occurs. Periodic audits confirm the budget discipline is operating.

## Failure correction

Common failure modes: the SLO is aspirational and not actually used (correct: tie release decisions to the actual SLO measurement); the budget is silently reset without review (correct: require a documented decision to reset); the budget is consumed but releases continue (correct: enforce the policy and pause releases); the SLO is adjusted to game the budget (correct: require a documented justification for SLO changes with stakeholder review); reliability work is deferred until the budget resets (correct: prioritize reliability work continuously, not just at budget exhaustion).

## Limitations

The error budget model assumes the organization can choose between reliability work and feature work. For services that must remain highly reliable, the error budget may be very small; in that case, the model still works but the release cadence is constrained. The model does not address every reliability concern (security incidents, data integrity issues) which may require separate handling.

## Scope note

This article summarizes project-neutral operations application of SRE release coordination and error budget practices. It does not assert any specific service's conformance or claim any certification outcome.

## Canonical sources

- Google SRE Book — SLO engineering and error budgets: https://sre.google/sre-book/service-level-objectives/
- Google SRE Workbook — SLO error budgets: https://sre.google/workbook/alerting-on-slos/
- Implementing Service Level Objectives (O'Reilly book): https://www.oreilly.com/library/view/implementing-service-level/9781492076811/