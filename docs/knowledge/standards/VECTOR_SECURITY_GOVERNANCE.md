# Vector Security Governance

## 1. Scope

Govern the security posture of vector retrieval systems (Milvus, Qdrant, pgvector) and embedding pipelines operated by OrchestrAI. Covers authentication, authorization, encryption, threat modelling, and incident response for vector workloads.

Excludes general database security controls (which are governed by [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md) and related standards) and excludes application-layer LLM security controls (governed by [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)).

## 2. Normative references

- [Vector Retrieval Governance](VECTOR_RETRIEVAL_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [Milvus Vector Database Version Governance](../reference/MILVUS_VERSION_GOVERNANCE.md)
- [Qdrant Vector Search Version Governance](../reference/QDRANT_VERSION_GOVERNANCE.md)
- [pgvector Version Governance](../reference/PGVECTOR_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [ISO/IEC 27402:2024 AI Security Governance](ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)
- [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Vector store** — a system that persists and indexes vectors for similarity retrieval.
- **Embedding inversion** — an attack that attempts to recover source content from an embedding vector.
- **Retrieval leakage** — unauthorized disclosure of indexed content via a retrieval query.
- **Tenant scope** — a logical boundary that confines queries and writes to a single tenant.

## 4. Threat model

The standard threat model for vector workloads includes:

1. **Embedding inversion** — recovering source text or attributes from a stolen embedding.
2. **Retrieval leakage** — cross-tenant reads caused by mis-scoped filters or bypassed access checks.
3. **Prompt injection via retrieved context** — indirect prompt injection from malicious content indexed into the vector store; tracked under [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md).
4. **Index poisoning** — malicious content intentionally indexed to influence downstream model behaviour.
5. **Credential theft** — exfiltration of API keys or database credentials.
6. **Snapshot exfiltration** — unauthorized copy of a vector snapshot or backup.

Each threat is mapped to a control in this standard and reviewed annually.

## 5. Authentication and authorization

1. All client access requires authentication; legacy username/password authentication on vector stores is prohibited.
2. Authorization is enforced at the access layer; vector stores must not rely on application code alone.
3. Multi-tenant collections must enforce tenant scoping via a mandatory filter; queries without a tenant filter are rejected.
4. Privileged operations (snapshot export, index rebuild, configuration changes) require break-glass credentials and produce an audit event.

## 6. Encryption

1. TLS 1.2+ is required for all client and inter-node traffic.
2. Vector data at rest is encrypted using envelope encryption with keys stored in the central KMS; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
3. Snapshots and backups inherit the encryption posture of the source store.
4. Personal-data embeddings are encrypted with a tenant-scoped key; key rotation follows the KMS rotation policy.

## 7. Input validation and indexing controls

1. Source content is validated and sanitized before indexing; HTML, JavaScript, and SQL fragments are neutralized.
2. Documents are tagged with a source-of-truth trust level that is propagated to the retrieval payload.
3. Untrusted content is indexed into an isolated collection or namespace; downstream applications must filter on the trust tag.
4. Index updates from third-party sources require a change ticket and a security review.

## 8. Retrieval safety

1. Retrieval results returned to an LLM must include the source identifier and trust tag so the model can apply its own guardrails.
2. Retrieved content that contains personal data is subject to the data-minimization rule: only the minimum necessary content is returned.
3. Indirect prompt-injection mitigations follow [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md).
4. The recall budget and the safety budget are tracked separately; safety regressions trigger an alert independent of recall drift.

## 9. Logging and monitoring

1. All authentication attempts, authorization decisions, and privileged operations produce audit events; see [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md).
2. Retrieval queries are sampled and reviewed for cross-tenant leakage at least quarterly.
3. Anomaly detection alerts on unusual query patterns (sudden spike in top-K, repeated queries on the same vector ID, queries outside business hours).
4. Dashboards for auth failures, tenant-scope violations, and recall-budget alerts are owned by the security and platform teams jointly.

## 10. Incident response

1. Suspected embedding inversion, retrieval leakage, or index poisoning triggers the standard security incident response process.
2. Affected collections are quarantined within one hour of incident confirmation.
3. The incident post-mortem identifies the lineage record of the affected vectors and the workload specification that permitted the exposure.
4. Post-incident actions are tracked in the remediation backlog and reviewed at the monthly platform guild.

## 11. Operating model

1. The Security team owns the threat model, the security review process, and the incident response process.
2. The Vector Platform team owns the implementation of the controls in this standard across shared infrastructure.
3. Workload owners are accountable for tenant scoping, source validation, and downstream safety controls.
4. The security and platform guilds meet jointly each quarter to review the threat model and the control coverage.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Security owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
