# Graph Database Incident Response Playbook

## Purpose

Respond to security and reliability incidents affecting graph databases (Neo4j, Amazon Neptune, Memgraph) and graph pipelines. The playbook aligns with [Graph Query Safety & Performance Governance](../standards/GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md), [Graph Database Architecture Governance](../standards/GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md), [Graph Data Lineage Governance](../standards/GRAPH_DATA_LINEAGE_GOVERNANCE.md), and the standard security incident response process.

## Audience

On-call engineers, security responders, workload owners, Graph Platform engineers.

## Pre-conditions

1. The standard incident severity levels and the on-call rotation are documented.
2. The graph database reference card is current (`NEO4J_VERSION_GOVERNANCE.md`, `NEPTUNE_VERSION_GOVERNANCE.md`, `MEMGRAPH_VERSION_GOVERNANCE.md`).
3. Audit logging is enabled and routed to the central SIEM; see [Audit Event Coverage Review](AUDIT_EVENT_COVERAGE_REVIEW.md).
4. Backup and snapshot retention meet the standard requirements; see [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
5. The query-latency SLO alert, the cartesian-explosion alert, and the tenant-scope alert are wired to the on-call paging rotation.

## Procedure

1. **Detect and triage.** Identify the incident class: cartesian explosion, long-traversal DoS, Cypher / SPARQL / Gremlin injection, cache poisoning, cross-tenant traversal, index bypass, query-latency SLO breach, or availability outage. Assign severity using the standard matrix.
2. **Contain.** Reject malicious queries via the access layer; revoke the implicated service-account credentials; freeze the load pipeline if the incident involves source ingestion; isolate the affected cluster or schema.
3. **Eradicate.** Rotate credentials, rebuild the schema from a known-good snapshot, and remove malicious elements. Confirm the threat is no longer present before recovery.
4. **Recover.** Re-enable queries; restore the workload to the previous query-latency SLO; verify tenant scoping, lineage integrity, and index usage before lifting the freeze.
5. **Communicate.** Issue stakeholder updates on the standard incident cadence; for regulated workloads, notify the AI Governance Council and the privacy officer within the SLA.
6. **Investigate.** Reconstruct the timeline from access logs, audit logs, and OTLP traces; identify the affected elements via the lineage record; quantify the exposure (tenant, element count, data class).
7. **Document.** Write the incident report with the timeline, the root cause, the affected workload specification, the SLO that was breached, and the customer impact.
8. **Remediate.** Open remediation tickets for control gaps; update the threat model and the workload specification; schedule the verification review.
9. **Verify.** Re-run the security review checklist and the query-latency regression suite before closing the incident.
10. **Learn.** Present the incident at the monthly platform guild; incorporate the lessons learned into [Graph Query Safety & Performance Governance](../standards/GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md) at the next 180-day review.

## Rollback

1. If the freeze causes a workload outage, switch the workload back to the previous data source (relational database, prior graph database, or pre-computed table).
2. If the rebuild fails, restore the schema from the most recent immutable snapshot; document the data gap.
3. If the credential rotation breaks a downstream system, roll back the rotation using the break-glass procedure and re-issue scoped credentials.
4. Communicate the rollback to stakeholders via the standard incident communication channel.
5. Open a follow-up ticket to address the rollback's root cause before re-attempting recovery.

## References

- [Graph Query Safety & Performance Governance](../standards/GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md)
- [Graph Database Architecture Governance](../standards/GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md)
- [Graph Data Lineage Governance](../standards/GRAPH_DATA_LINEAGE_GOVERNANCE.md)
- [Neo4j Graph Database Version Governance](../reference/NEO4J_VERSION_GOVERNANCE.md)
- [Amazon Neptune Graph Database Version Governance](../reference/NEPTUNE_VERSION_GOVERNANCE.md)
- [Memgraph In-Memory Graph Database Version Governance](../reference/MEMGRAPH_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](../standards/OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [Audit Event Coverage Review](AUDIT_EVENT_COVERAGE_REVIEW.md)
- [Audit Storage Capacity Review](AUDIT_STORAGE_CAPACITY_REVIEW.md)
- [Encryption Coverage Review](ENCRYPTION_COVERAGE_REVIEW.md)
