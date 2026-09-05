---
title: "Disaster Recovery Failover Playbook"
owner: "Resilience Program Manager"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Disaster Recovery Failover Playbook

## Trigger

Use this playbook when a disaster or major disruption has rendered a primary site, region, or set of systems unavailable, when failover to a secondary site is required to meet recovery time objectives, or when a planned failover exercise is being executed.

## Scope

Apply the process to mission-critical systems, supporting infrastructure, data replication targets, dependent services, and the operational, communications, and validation procedures required to bring secondary systems into service.

## Inputs

- disaster declaration (event, scope, severity, time of failure);
- RTO/RPO targets for in-scope systems;
- DR runbook and topology (active-passive, pilot light, warm standby, multi-region active-active);
- replication and data-integrity state;
- communication and escalation paths.

## Steps

1. **Confirm the trigger.** Validate the disaster declaration, the affected scope, and the decision to initiate failover; record the authority and timestamp.
2. **Notify stakeholders.** Engage executive leadership, on-call rotations, dependent teams, suppliers, and customers through the incident communications playbook.
3. **Stabilize the primary site if possible.** If recovery of the primary site is the chosen path, lock the primary site to prevent failover oscillation and limit further damage.
4. **Bring secondary site to active state.** Stand up the secondary infrastructure, warm the data stores, verify replication is current, and bring services into operation in the documented order.
5. **Validate integrity.** Verify data consistency, transaction catch-up, certificate and key validity, dependency health, and configuration alignment with the primary site.
6. **Reroute traffic.** Update DNS, load balancer, or service-mesh configuration to direct traffic to the secondary site; verify user-facing functionality.
7. **Communicate externally.** Notify customers, partners, and regulators of the failover and any service disruption per the incident communications playbook.
8. **Operate under degraded mode.** Run on the secondary site under documented degraded-mode operations; track any functional gaps against RTO/RPO.
9. **Recover the primary site.** Once the primary site is restorable, plan re-failover with appropriate data reconciliation and validation.
10. **Repatriate.** Re-failover during a planned window once the primary site is verified; verify data consistency at each step; document any data discrepancies.
11. **Close and learn.** Conduct a post-incident review; document decisions, timeline, RTO/RPO achievement, gaps, and corrective actions.

## Escalation

Escalate to the Resilience Program Manager, Service Owner, and Executive Sponsors when:
- the failover time exceeds the documented RTO;
- data integrity issues are detected during failover or re-failover;
- customer-facing or regulated workloads are affected;
- multiple regions or business units are involved.

## Evidence

- disaster declaration, scope, and authorization;
- failover timeline and decision rationale;
- data consistency and integrity validation results;
- communications artifacts and status page entries;
- post-incident review document and corrective actions.

## Completion Criteria

The DR failover is considered complete when:
- secondary site is validated and serving traffic within RTO;
- data consistency and integrity are verified within RPO;
- communications and status updates have been delivered;
- primary site recovery and re-failover are executed or scheduled.

## Exceptions

Document deviations with the approver, scope, expiration, compensating control, and review schedule. Where data loss exceeds RPO, document it as a separate incident with its own post-mortem.

## Related Documents

- [NIST SP 800-34 Contingency Planning](../reference/NIST_SP_800_34_CONTINGENCY_PLANNING.md)
- [ISO 22301 Business Continuity Management](../reference/ISO_22301_BUSINESS_CONTINUITY_MANAGEMENT.md)
- [Site Reliability Engineering On-Call Response](SITE_RELIABILITY_ENGINEERING_ON_CALL_RESPONSE.md)
- [Backup and Restore Validation](BACKUP_RESTORE_VALIDATION.md)
