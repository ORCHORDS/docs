---
title: "Site Reliability Engineering On-Call Response Playbook"
owner: "SRE Manager"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Site Reliability Engineering On-Call Response Playbook

## Trigger

Use this playbook when an alert fires or a service degradation is reported that requires on-call engineering response, and for the operational handoff, escalation, and stabilization activities that follow until the service is restored to defined SLOs.

## Scope

Apply the process to production services, supporting infrastructure, dependent third-party services, and the on-call rotations, paging systems, runbooks, and incident management tooling used by the SRE team.

## Inputs

- alert payload, source, and severity;
- service catalog entry, SLOs, error budgets, and dependency map;
- runbooks and known-issue documentation;
- on-call schedule, escalation policy, and contact tree;
- recent change log and deployment history.

## Steps

1. **Acknowledge the page.** Acknowledge within the on-call SLO; if unable to engage within the threshold, the secondary on-call or escalation policy is triggered.
2. **Open an incident.** Record severity, declaration time, incident lead, scribe, and communications lead; link the alert, the service, and any related incidents.
3. **Stabilize first.** Apply the lowest-risk mitigation that restores the user-visible SLO; prefer rollback, feature flag toggle, traffic shift, capacity increase, or dependency disable over novel code changes.
4. **Communicate.** Post initial status within the documented window; publish updates at the cadence appropriate to severity; route external communications through the authorized channel.
5. **Investigate in parallel.** Identify contributing changes, recent deployments, dependency incidents, and capacity exhaustion; record hypotheses and evidence.
6. **Mitigate the root cause.** Once stable, apply the durable fix; verify the fix in production with appropriate telemetry before declaring the incident resolved.
7. **Manage capacity and dependency.** Engage with dependent service owners, capacity planning, and external providers when the incident crosses a boundary.
8. **Declare resolution.** Confirm SLO compliance is restored; close the incident; archive the timeline, decisions, and artifacts.
9. **Hand off.** Brief the next on-call shift on residual risk, open actions, and watch items; ensure paging thresholds remain appropriate.
10. **Run a post-incident review.** Schedule the review within the documented window; identify contributing factors, action items, and improvements to detection, response, and prevention.

## Escalation

Escalate per the documented policy when:
- an SLO is breached beyond the error budget allowance;
- the incident crosses service or business unit boundaries;
- a suspected security, privacy, or safety dimension is identified;
- the on-call cannot stabilize the service within the response SLO.

## Evidence

- alert payload, acknowledgment timestamp, incident ID;
- timeline of detection, mitigation, and resolution;
- runbook execution log and decision rationale;
- communications artifacts and status-page entries;
- post-incident review document and action items.

## Completion Criteria

The response is considered complete when:
- the service is restored to defined SLOs;
- the incident is closed with a complete timeline;
- communications are archived and stakeholders informed;
- post-incident review is scheduled or completed for qualifying incidents.

## Exceptions

Document deviations from runbook steps, response time SLOs, or severity classification with rationale, approver, compensating controls, and review date.

## Related Documents

- [Google SRE Book — Incident Management](GOOGLE_SRE_INCIDENT_MANAGEMENT.md)
- [ITIL 4 Incident Management Practice](ITIL_4_INCIDENT_MANAGEMENT_PRACTICE.md)
- [Service Level Objective Definition](SERVICE_LEVEL_OBJECTIVE_DEFINITION.md)
- [Error Budget Policy](ERROR_BUDGET_POLICY.md)
- [Blameless Post-Incident Review](BLAMELESS_POST_INCIDENT_REVIEW.md)
