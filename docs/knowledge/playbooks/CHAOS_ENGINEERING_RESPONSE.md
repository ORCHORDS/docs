---
title: "Chaos Engineering Playbook"
owner: "SRE Manager"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Chaos Engineering Playbook

## Trigger

Use this playbook when a hypothesis about system resilience must be validated in production-like environments, when a recent incident suggests a missed weakness, when a new dependency or topology is introduced, or when a recurring validation cadence must be established or re-baselined.

## Scope

Apply the process to production, pre-production, and staging environments where experiments are scoped, blast-radius-bounded, and authorized; to systems of record that may be impacted; and to the supporting observability, rollback, and incident response tooling.

## Inputs

- steady-state hypothesis and metric;
- experiment design (fault to inject, blast radius, abort conditions);
- target environment, scope, and traffic profile;
- rollback plan and abort criteria;
- approval and notification list.

## Steps

1. **Define the steady state.** Express the hypothesis as a measurable condition (latency SLO, error rate, queue depth) under normal operation; confirm the metric is instrumented.
2. **Design the experiment.** Choose the fault class (latency, error, resource exhaustion, dependency failure, region, certificate expiry); specify blast radius and abort conditions.
3. **Coordinate and notify.** Notify stakeholders, on-call, and dependent teams; record the approval and the start time.
4. **Run the experiment.** Inject the fault within the bounded scope; observe the steady-state metric and the wider system; capture relevant traces, logs, and telemetry.
5. **Verify rollback.** Confirm the experiment can be reverted cleanly under controlled conditions; confirm safety mechanisms (circuit breakers, kill switches) work as intended.
6. **Record observations.** Document the hypothesis, observed behavior, telemetry, and any surprise behavior; annotate unplanned consequences.
7. **Abort if needed.** Halt the experiment immediately on abort conditions or unintended impact outside the bounded scope; document the abort reason.
8. **Remediate findings.** Open corrective actions for unhandled failure modes; strengthen tests, automation, or controls where required.
9. **Schedule continuous validation.** Promote successful, safe experiments to continuous execution in lower environments; re-run periodically to detect regressions.
10. **Close and learn.** Update architecture documentation, runbooks, and training based on findings; track related incidents to verify improvement.

## Escalation

Escalate to the SRE Manager, Service Owner, and Incident Response when:
- the experiment triggers an unplanned production impact;
- the experiment reveals a critical or exploitable weakness;
- a regulatory or contractual boundary is crossed;
- rollback cannot be executed as designed.

## Evidence

- experiment design, hypothesis, and approvals;
- recorded steady-state metric and post-fault telemetry;
- abort conditions and rollback execution logs;
- findings register and corrective actions;
- continuous validation schedule and run history.

## Completion Criteria

The chaos experiment is considered complete when:
- the hypothesis was tested within the bounded scope;
- the steady state was measured before, during, and after;
- rollback was verified;
- findings and corrective actions are documented and tracked.

## Exceptions

Document deviations with the approver, scope, expiration, compensating control, and review schedule. Production experimentation should be the exception, not the norm; pre-production and production-mirroring environments are the default.

## Related Documents

- [Principles of Chaos Engineering](PRINCIPLES_OF_CHAOS_ENGINEERING.md)
- [NIST SP 800-84 Test, Training, and Exercise Programs](NIST_SP_800_84_TEST_TRAINING_EXERCISE.md)
- [Google SRE Book — Release Engineering](GOOGLE_SRE_RELEASE_ENGINEERING.md)
- [Site Reliability Engineering On-Call Response](SITE_RELIABILITY_ENGINEERING_ON_CALL_RESPONSE.md)
