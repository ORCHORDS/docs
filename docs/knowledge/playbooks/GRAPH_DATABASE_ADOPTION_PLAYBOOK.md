# Graph Database Adoption Playbook

## Purpose

Adopt a graph database (Neo4j, Amazon Neptune, Memgraph, or managed equivalent) for a new workload that requires graph traversals, knowledge-graph representations, or graph-augmented retrieval. The playbook aligns with [Graph Database Architecture Governance](../standards/GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md), [Graph Query Safety & Performance Governance](../standards/GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md), and [Graph Data Lineage Governance](../standards/GRAPH_DATA_LINEAGE_GOVERNANCE.md).

## Audience

Workload owners, Graph Platform engineers, data engineers, security reviewers.

## Pre-conditions

1. The graph database reference card is current (`NEO4J_VERSION_GOVERNANCE.md`, `NEPTUNE_VERSION_GOVERNANCE.md`, `MEMGRAPH_VERSION_GOVERNANCE.md`).
2. AI Impact Assessment is filed for the workload; see [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md).
3. Tenant scoping and data-classification decisions are documented.
4. Source datasets are registered in the catalogue with documented freshness and retention.
5. A representative query set is available or scheduled for capture.

## Procedure

1. **Select the graph database.** Choose Neo4j for property-graph + Graph Data Science; choose Neptune for AWS-native managed deployment; choose Memgraph for high-throughput transactional workloads.
2. **Select the graph model.** Choose property-graph for typed entities and relationships; choose RDF for W3C-standard semantics.
3. **Select the query language.** Choose openCypher for property-graph; SPARQL for RDF; Gremlin only when openCypher / SPARQL performance is insufficient.
4. **Provision the cluster.** Apply the platform Helm chart or Terraform module pinned to the supported minor; record the cluster manifest in the inventory.
5. **Configure authentication and authorization.** Provision workload-scoped service-account credentials in the central secret backend; enable OIDC for interactive users; disable legacy username/password authentication.
6. **Author the schema.** Declare node labels, relationship types, property keys, indexes, constraints, and AI risk tier. Register the schema in the Graph Platform registry.
7. **Wire lineage.** Emit lineage records with every element write; reject elements without a complete lineage record.
8. **Validate query safety.** Run the representative query set against the staging cluster; verify traversal limits, cartesian-explosion protection, tenant scoping, and index usage.
9. **Wire observability.** Enable Prometheus metrics, OTLP traces, query-latency SLO dashboards, and tenant-scope alerts following the standard observability requirements.
10. **Run a security review.** Walk through the [Graph Query Safety & Performance Governance](../standards/GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md) threat model; document mitigations and residual risk; file waivers for any unmet controls.
11. **Pilot in staging.** Route 5% of production traffic to the staging cluster; compare query latency, error rate, and tenant scoping with the baseline.
12. **Promote to production.** Enable the production cluster; set the query-latency SLO alert, the cartesian-explosion alert, and the tenant-scope alert; hand off to the on-call rotation.
13. **Adopt the operating cadence.** Schedule the quarterly determinism regression, the annual threat-model review, and the 180-day standard review.

## Rollback

1. Stop the load pipelines and freeze new element writes.
2. Switch the workload back to the previous data source (relational database, prior graph database, or pre-computed table).
3. Quarantine the schema for forensic review; do not delete until the security review is complete.
4. Open a remediation ticket that captures the query latency regression, the tenant-scope breach, or the security finding.
5. Communicate the rollback to stakeholders via the standard incident communication channel.
6. Update the workload specification with the lessons learned before the next adoption attempt.

## References

- [Graph Database Architecture Governance](../standards/GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md)
- [Graph Query Safety & Performance Governance](../standards/GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md)
- [Graph Data Lineage Governance](../standards/GRAPH_DATA_LINEAGE_GOVERNANCE.md)
- [Neo4j Graph Database Version Governance](../reference/NEO4J_VERSION_GOVERNANCE.md)
- [Amazon Neptune Graph Database Version Governance](../reference/NEPTUNE_VERSION_GOVERNANCE.md)
- [Memgraph In-Memory Graph Database Version Governance](../reference/MEMGRAPH_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Vector Retrieval Governance](../standards/VECTOR_RETRIEVAL_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
