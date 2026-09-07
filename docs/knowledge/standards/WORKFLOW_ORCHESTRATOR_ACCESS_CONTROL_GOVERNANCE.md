# Workflow Orchestrator Access Control Governance

## 1. Scope

Govern the authentication, authorization, and audit posture of workflow orchestrators (Dagster, Prefect, Apache Airflow, Temporal, Argo Workflows, and equivalents) and workflow pipelines operated by OrchestrAI. Covers identity, RBAC, tenant scoping, secret handling, threat modelling, and incident response for workflow workloads.

Excludes general database access controls, which are governed by [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md) and related standards. Excludes feature-store access controls, which are governed by [Feature Store Access Control Governance](FEATURE_STORE_ACCESS_CONTROL_GOVERNANCE.md).

## 2. Normative references

- [Workflow Orchestrator Architecture Governance](WORKFLOW_ORCHESTRATOR_ARCHITECTURE_GOVERNANCE.md)
- [Workflow Lineage & Reproducibility Governance](WORKFLOW_LINEAGE_REPRODUCIBILITY_GOVERNANCE.md)
- [Dagster Data Orchestrator Version Governance](../reference/DAGSTER_VERSION_GOVERNANCE.md)
- [Prefect Workflow Orchestrator Version Governance](../reference/PREFECT_VERSION_GOVERNANCE.md)
- [Apache Airflow Workflow Orchestrator Version Governance](../reference/AIRFLOW_VERSION_GOVERNANCE.md)
- [Temporal Durable Execution Version Governance](../reference/TEMPORAL_VERSION_GOVERNANCE.md)
- [Argo Workflows / Argo CD / Argo Events / Argo Rollouts Version Governance](../reference/ARGO_VERSION_GOVERNANCE.md)
- [Feature Store Access Control Governance](FEATURE_STORE_ACCESS_CONTROL_GOVERNANCE.md)
- [Vector Security Governance](VECTOR_SECURITY_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [ISO/IEC 27402:2024 AI Security Governance](ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)
- [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Orchestrator** — a system that schedules and executes workflows on target compute engines.
- **Tenant scope** — a logical boundary that confines reads and writes to a single tenant.
- **Secret backend** — an external system that stores and retrieves connection strings, credentials, and other secrets used by workflows.
- **Backfill breach** — unauthorized regeneration of historical outputs that may overwrite legitimate values.

## 4. Threat model

The standard threat model for workflow workloads includes:

1. **Cross-tenant execution** — a tenant triggers a workflow that reads or writes data belonging to another tenant because of a missing or bypassed tenant filter.
2. **Secret exfiltration** — an attacker extracts connection strings or credentials from the metadata database, the secret backend, or a workflow log.
3. **Backfill breach** — an attacker triggers a backfill that overwrites legitimate historical outputs with attacker-controlled values.
4. **Code-location takeover** — an attacker registers a malicious code location that ships with the orchestrator and runs inside the worker process.
5. **Credential theft** — exfiltration of orchestrator API keys or service-account credentials.
6. **Schedule tampering** — an attacker modifies a schedule to trigger workflows at unintended times or with attacker-controlled parameters.

Each threat is mapped to a control in this standard and reviewed annually.

## 5. Identity and authentication

1. All client access requires authentication; legacy username/password authentication on orchestrators is prohibited.
2. Service-account credentials are scoped per workflow / code location and rotated at least every 90 days.
3. Federated identity (OIDC) is the default for interactive users; see [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md) for the secret-rotation pipeline.
4. Break-glass credentials require two-person approval and produce an audit event.

## 6. Authorization and tenant scoping

1. Authorization is enforced at the access layer; orchestrators must not rely on application code alone.
2. Multi-tenant workflows enforce tenant scoping via a mandatory runtime parameter; workflows without a tenant parameter are rejected.
3. Privileged operations (registry export, code-location registration, schedule modification) require privileged credentials and produce an audit event.
4. Cross-tenant triggers are prohibited; the access layer rejects any trigger whose tenant parameter does not match the caller's identity.

## 7. Secret handling

1. All connection strings, credentials, and tokens are stored in the central secret backend; plaintext credentials in DAG / flow / asset code are prohibited.
2. The secret backend is the source of truth; orchestrators may cache secrets for the duration of a run but must not persist them across runs.
3. Secret rotation is automated via the secret-rotation pipeline; rotated secrets propagate to running workers on the standard refresh cadence.
4. Secret access is logged to the central audit pipeline; see [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md).

## 8. Code-location and image integrity

1. Code locations are signed by the workload owner and verified by the orchestrator at registration time.
2. Worker container images are signed and pinned to a digest; the orchestrator rejects unsigned or unpinned images.
3. Code-location registration and image update events produce audit events.
4. New code locations affecting regulated workloads require a security review.

## 9. Encryption

1. TLS 1.2+ is required for all client and inter-node traffic.
2. Workflow data at rest is encrypted using envelope encryption with keys stored in the central KMS; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
3. Backups inherit the encryption posture of the source store.
4. Personal-data outputs are encrypted with a tenant-scoped key; key rotation follows the KMS rotation policy.

## 10. Audit logging

1. All authentication attempts, authorization decisions, and privileged operations produce audit events; see [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md).
2. Audit events include `actor`, `workflow`, `workflow_version`, `task`, `operation`, `source_ip`, and `user_agent`.
3. Audit logs are replicated to the central SIEM with retention of at least 24 months.
4. Anomaly detection alerts on unusual workflow patterns (sudden spike in backfills, repeated triggers of the same workflow, triggers outside business hours).

## 11. Incident response

1. Suspected cross-tenant execution, secret exfiltration, backfill breach, code-location takeover, credential theft, or schedule tampering triggers the standard security incident response process.
2. Affected workflows are paused within one hour of incident confirmation.
3. The incident post-mortem identifies the lineage record of the affected outputs and the workload specification that permitted the exposure.
4. Post-incident actions are tracked in the remediation backlog and reviewed at the monthly platform guild.

## 12. Operating model

1. The Security team owns the threat model, the security review process, and the incident response process.
2. The Workflow Platform team owns the implementation of the controls in this standard across shared infrastructure.
3. Workflow owners are accountable for tenant scoping, secret handling, and code-location review.
4. The security and platform guilds meet jointly each quarter to review the threat model and the control coverage.

## 13. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Security owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 14. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
