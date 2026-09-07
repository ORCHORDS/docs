# Workflow Orchestrator Incident Response Playbook

## Purpose

Respond to security and reliability incidents affecting workflow orchestrators (Dagster, Prefect, Apache Airflow, Temporal, Argo Workflows) and workflow pipelines. The playbook aligns with [Workflow Orchestrator Access Control Governance](../standards/WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md), [Workflow Orchestrator Architecture Governance](../standards/WORKFLOW_ORCHESTRATOR_ARCHITECTURE_GOVERNANCE.md), and the standard security incident response process.

## Audience

On-call engineers, security responders, workflow owners, Workflow Platform engineers.

## Pre-conditions

1. The standard incident severity levels and the on-call rotation are documented.
2. The orchestrator reference card is current (`DAGSTER_VERSION_GOVERNANCE.md`, `PREFECT_VERSION_GOVERNANCE.md`, `AIRFLOW_VERSION_GOVERNANCE.md`, `TEMPORAL_VERSION_GOVERNANCE.md`, `ARGO_VERSION_GOVERNANCE.md`).
3. Audit logging is enabled and routed to the central SIEM.
4. Backup and snapshot retention meet the standard requirements; see [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
5. The runtime SLO alert, the schedule-failure alert, and the lineage-integrity alert are wired to the on-call paging rotation.

## Procedure

1. **Detect and triage.** Identify the incident class: cross-tenant execution, secret exfiltration, backfill breach, code-location takeover, credential theft, schedule tampering, runtime SLO breach, or availability outage. Assign severity using the standard matrix.
2. **Contain.** Pause the affected workflows via the orchestrator's pause API; revoke the implicated service-account credentials; freeze the schedule and sensor pipelines if the incident involves source ingestion.
3. **Eradicate.** Rotate credentials, rebuild workflow definitions from a known-good code-location snapshot, and remove malicious code locations from the registry. Confirm the threat is no longer present before recovery.
4. **Recover.** Re-enable workflows; restore the workload to the previous runtime SLO; verify tenant scoping and lineage integrity before lifting the pause.
5. **Communicate.** Issue stakeholder updates on the standard incident cadence; for regulated workloads, notify the AI Governance Council and the privacy officer within the SLA.
6. **Investigate.** Reconstruct the timeline from audit logs and OTLP traces; identify the affected outputs via the lineage record; quantify the exposure (tenant, output count, data class, downstream consumers impacted).
7. **Document.** Write the incident report with the timeline, the root cause, the affected workload specification, the runtime SLO that was breached, and the customer impact.
8. **Remediate.** Open remediation tickets for control gaps; update the threat model and the workload specification; schedule the verification review.
9. **Verify.** Re-run the security review checklist and the determinism regression suite before closing the incident.
10. **Learn.** Present the incident at the monthly platform guild; incorporate the lessons learned into [Workflow Orchestrator Access Control Governance](../standards/WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md) at the next 180-day review.

## Rollback

1. If the pause causes a workload outage, switch the workload back to the previous scheduling source (cron, manual triggers, or prior orchestrator).
2. If the rebuild fails, restore from the most recent immutable snapshot; document the data gap.
3. If the credential rotation breaks a downstream system, roll back the rotation using the break-glass procedure and re-issue scoped credentials.
4. Communicate the rollback to stakeholders via the standard incident communication channel.
5. Open a follow-up ticket to address the rollback's root cause before re-attempting recovery.

## References

- [Workflow Orchestrator Access Control Governance](../standards/WORKFLOW_ORCHESTRATOR_ACCESS_CONTROL_GOVERNANCE.md)
- [Workflow Orchestrator Architecture Governance](../standards/WORKFLOW_ORCHESTRATOR_ARCHITECTURE_GOVERNANCE.md)
- [Workflow Lineage & Reproducibility Governance](../standards/WORKFLOW_LINEAGE_REPRODUCIBILITY_GOVERNANCE.md)
- [Dagster Data Orchestrator Version Governance](../reference/DAGSTER_VERSION_GOVERNANCE.md)
- [Prefect Workflow Orchestrator Version Governance](../reference/PREFECT_VERSION_GOVERNANCE.md)
- [Apache Airflow Workflow Orchestrator Version Governance](../reference/AIRFLOW_VERSION_GOVERNANCE.md)
- [Temporal Durable Execution Version Governance](../reference/TEMPORAL_VERSION_GOVERNANCE.md)
- [Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance](../reference/ARGO_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [ISO/IEC 27402:2024 AI Security Governance](../standards/ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md)
- [Audit Event Coverage Review](AUDIT_EVENT_COVERAGE_REVIEW.md)
- [Audit Storage Capacity Review](AUDIT_STORAGE_CAPACITY_REVIEW.md)
- [Encryption Coverage Review](ENCRYPTION_COVERAGE_REVIEW.md)
