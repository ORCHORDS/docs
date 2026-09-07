# Vector Incident Response Playbook

## Purpose

Respond to security and reliability incidents affecting vector retrieval systems (Milvus, Qdrant, pgvector) and embedding pipelines. The playbook aligns with [Vector Security Governance](../standards/VECTOR_SECURITY_GOVERNANCE.md), [Vector Retrieval Governance](../standards/VECTOR_RETRIEVAL_GOVERNANCE.md), and the standard security incident response process.

## Audience

On-call engineers, security responders, workload owners, Vector Platform engineers, AI Governance Council reviewers.

## Pre-conditions

1. The standard incident severity levels and the on-call rotation are documented.
2. The vector store reference card is current (`MILVUS_VERSION_GOVERNANCE.md`, `QDRANT_VERSION_GOVERNANCE.md`, `PGVECTOR_VERSION_GOVERNANCE.md`).
3. Audit logging is enabled and routed to the central SIEM.
4. Backup and snapshot retention meet the standard requirements; see [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
5. The recall-budget alert and the safety-budget alert are wired to the on-call paging rotation.

## Procedure

1. **Detect and triage.** Identify the incident class: embedding inversion, retrieval leakage, index poisoning, credential theft, snapshot exfiltration, recall regression, or availability outage. Assign severity using the standard matrix.
2. **Contain.** Quarantine the affected collections by toggling the cluster policy controller; revoke the implicated API keys; freeze the embedding pipeline if the incident involves source ingestion.
3. **Eradicate.** Rotate credentials, rebuild indexes from a known-good snapshot, and remove malicious content from the dataset snapshots. Confirm the threat is no longer present before recovery.
4. **Recover.** Re-enable reads; restore the workload to the previous recall budget; verify tenant-scoping and lineage integrity before lifting the quarantine.
5. **Communicate.** Issue stakeholder updates on the standard incident cadence; for regulated workloads, notify the AI Governance Council and the privacy officer within the SLA.
6. **Investigate.** Reconstruct the timeline from audit logs and OTLP traces; identify the affected vectors via the lineage record; quantify the exposure (tenant, vector count, data class).
7. **Document.** Write the incident report with the timeline, the root cause, the affected workload specification, the recall or safety budget that was breached, and the customer impact.
8. **Remediate.** Open remediation tickets for control gaps; update the threat model and the workload specification; schedule the verification review.
9. **Verify.** Re-run the security review checklist and the recall regression suite before closing the incident.
10. **Learn.** Present the incident at the monthly platform guild; incorporate the lessons learned into [Vector Security Governance](../standards/VECTOR_SECURITY_GOVERNANCE.md) at the next 180-day review.

## Rollback

1. If the quarantine causes a workload outage, switch the workload back to the previous retrieval path (keyword search or prior collection).
2. If the rebuild fails, restore from the most recent immutable snapshot; document the data gap.
3. If the credential rotation breaks a downstream system, roll back the rotation using the break-glass procedure and re-issue scoped credentials.
4. Communicate the rollback to stakeholders via the standard incident communication channel.
5. Open a follow-up ticket to address the rollback's root cause before re-attempting recovery.

## References

- [Vector Security Governance](../standards/VECTOR_SECURITY_GOVERNANCE.md)
- [Vector Retrieval Governance](../standards/VECTOR_RETRIEVAL_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](../standards/VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [Milvus Vector Database Version Governance](../reference/MILVUS_VERSION_GOVERNANCE.md)
- [Qdrant Vector Search Version Governance](../reference/QDRANT_VERSION_GOVERNANCE.md)
- [pgvector Version Governance](../reference/PGVECTOR_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [ISO/IEC 27402:2024 AI Security Governance](../standards/ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](../standards/OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [Audit Event Coverage Review](AUDIT_EVENT_COVERAGE_REVIEW.md)
- [Audit Storage Capacity Review](AUDIT_STORAGE_CAPACITY_REVIEW.md)
- [Encryption Coverage Review](ENCRYPTION_COVERAGE_REVIEW.md)
