# Feature Store Access Control Governance

## 1. Scope

Govern the authentication, authorization, and audit posture of feature stores (Feast, Tecton, Hopsworks Feature Store, and equivalents) and feature pipelines operated by OrchestrAI. Covers identity, RBAC, tenant scoping, encryption, threat modelling, and incident response for feature-store workloads.

Excludes general database access controls, which are governed by [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md) and related standards. Excludes model-serving access controls, which are governed by [KServe Model Serving Version Governance](../reference/KSERVE_VERSION_GOVERNANCE.md) and [Triton Inference Server Version Governance](../reference/TRITON_INFERENCE_SERVER_VERSION_GOVERNANCE.md).

## 2. Normative references

- [Feature Store Architecture Governance](FEATURE_STORE_ARCHITECTURE_GOVERNANCE.md)
- [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md)
- [Feast Open Source Feature Store Version Governance](../reference/FEAST_VERSION_GOVERNANCE.md)
- [Tecton Feature Platform Version Governance](../reference/TECTON_VERSION_GOVERNANCE.md)
- [Hopsworks Feature Store Version Governance](../reference/HOPSWORKS_FEATURE_STORE_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [ISO/IEC 27402:2024 AI Security Governance](ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)
- [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Feature store** — a system that ingests, transforms, stores, and serves feature values for training and inference.
- **Tenant scope** — a logical boundary that confines reads and writes to a single tenant.
- **Parity breach** — an unauthorised divergence between the online and offline views of a feature.
- **Lineage breach** — an unauthorised modification or deletion of a lineage record.

## 4. Threat model

The standard threat model for feature-store workloads includes:

1. **Cross-tenant retrieval** — a tenant reads feature values that belong to another tenant because of a missing or bypassed tenant filter.
2. **Parity breach** — an attacker modifies online feature values to bias downstream model behaviour, while offline values remain unchanged.
3. **Lineage breach** — an attacker rewrites lineage records to obscure the source of a feature value used by a regulated model.
4. **Credential theft** — exfiltration of feature-store API keys or service-account credentials.
5. **Snapshot exfiltration** — unauthorized copy of a feature snapshot or backup.
6. **Poisoned transformation** — an attacker introduces a malicious transformation that produces biased feature values.

Each threat is mapped to a control in this standard and reviewed annually.

## 5. Identity and authentication

1. All client access requires authentication; legacy username/password authentication on feature stores is prohibited.
2. Service-account credentials are scoped per workload and rotated at least every 90 days.
3. Federated identity (OIDC) is the default for interactive users; see [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md) for the secret-rotation pipeline.
4. Break-glass credentials require two-person approval and produce an audit event.

## 6. Authorization and tenant scoping

1. Authorization is enforced at the access layer; feature stores must not rely on application code alone.
2. Multi-tenant feature views enforce tenant scoping via a mandatory payload filter; queries without a tenant filter are rejected.
3. Privileged operations (registry export, snapshot creation, transformation registration) require privileged credentials and produce an audit event.
4. Cross-tenant queries are prohibited; the access layer rejects any query whose tenant filter does not match the caller's identity.

## 7. Encryption

1. TLS 1.2+ is required for all client and inter-node traffic.
2. Feature data at rest is encrypted using envelope encryption with keys stored in the central KMS; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
3. Snapshots and backups inherit the encryption posture of the source store.
4. Personal-data feature values are encrypted with a tenant-scoped key; key rotation follows the KMS rotation policy.

## 8. Audit logging

1. All authentication attempts, authorization decisions, and privileged operations produce audit events; see [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md).
2. Audit events include `actor`, `feature_view`, `feature_version`, `entity_key`, `operation`, `source_ip`, and `user_agent`.
3. Audit logs are replicated to the central SIEM with retention of at least 24 months.
4. Anomaly detection alerts on unusual query patterns (sudden spike in feature lookups, repeated queries on the same entity key, queries outside business hours).

## 9. Transformation safety

1. Transformation code is reviewed for security impact before registration; see [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md).
2. Transformation execution environments are isolated with no network egress to non-approved destinations.
3. Transformation parameters are validated against a schema; out-of-range or malformed parameters are rejected at registration time.
4. New transformations affecting regulated workloads require a security review.

## 10. Incident response

1. Suspected cross-tenant retrieval, parity breach, lineage breach, credential theft, or poisoned transformation triggers the standard security incident response process.
2. Affected feature views are quarantined within one hour of incident confirmation.
3. The incident post-mortem identifies the lineage record of the affected values and the workload specification that permitted the exposure.
4. Post-incident actions are tracked in the remediation backlog and reviewed at the monthly platform guild.

## 11. Operating model

1. The Security team owns the threat model, the security review process, and the incident response process.
2. The Feature Platform team owns the implementation of the controls in this standard across shared infrastructure.
3. Workload owners are accountable for tenant scoping, transformation review, and downstream model governance.
4. The security and platform guilds meet jointly each quarter to review the threat model and the control coverage.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Security owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
