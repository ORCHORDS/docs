---
title: "Operations Manual"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Operations Manual

## Purpose

Define company-wide operational expectations without publishing private
topology or provider configuration.

## Operating principles

- Every production service has an accountable owner.
- Critical operations have documented runbooks or SOPs.
- Monitoring should cover user impact and critical dependencies, not just host
  health.
- Alerts should be actionable and routed to people able to respond.
- High-risk changes use approval, verification, and rollback controls.
- Backups are not trusted until restoration is tested.
- Incidents preserve evidence and produce follow-up actions.
- Capacity, dependency, access, and lifecycle risks are reviewed regularly.

## Service ownership

Service owners are responsible for:

- defining service objectives and critical dependencies;
- ensuring operational documentation exists;
- reviewing access;
- maintaining monitoring and alerting;
- participating in incidents;
- validating backup/recovery expectations;
- accepting or escalating residual risk.

## Operational evidence

Retain appropriate records for high-impact changes, incidents, access reviews,
recovery tests, major maintenance, and release approvals.

## Related procedures

- [Change Management](CHANGE_MANAGEMENT.md)
- [Incident Response](INCIDENT_RESPONSE.md)
- [Business Continuity](BUSINESS_CONTINUITY.md)
- [Access Management](ACCESS_MANAGEMENT.md)
- [Change Control SOP](../sop/CHANGE_CONTROL_SOP.md)
- [Incident Management SOP](../sop/INCIDENT_MANAGEMENT_SOP.md)
- [Backup and Restore SOP](../sop/BACKUP_RESTORE_SOP.md)
