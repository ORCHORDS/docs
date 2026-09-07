# Graph Database Architecture Governance

## 1. Scope

Govern the architecture, selection, and operational use of graph databases (Neo4j, Amazon Neptune, Memgraph, and managed equivalents) across OrchestrAI products. Covers property-graph and RDF-graph workloads, query-language selection, indexing, and integration with feature, vector, and model serving subsystems.

Excludes the underlying compute and storage engines (Kubernetes, AWS-managed services) which are governed by their own cards. Excludes graph query safety and performance, which is governed by [Graph Query Safety & Performance Governance](GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md). Excludes graph data lineage, which is governed by [Graph Data Lineage Governance](GRAPH_DATA_LINEAGE_GOVERNANCE.md).

## 2. Normative references

- [Neo4j Graph Database Version Governance](../reference/NEO4J_VERSION_GOVERNANCE.md)
- [Amazon Neptune Graph Database Version Governance](../reference/NEPTUNE_VERSION_GOVERNANCE.md)
- [Memgraph In-Memory Graph Database Version Governance](../reference/MEMGRAPH_VERSION_GOVERNANCE.md)
- [Graph Query Safety & Performance Governance](GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md)
- [Graph Data Lineage Governance](GRAPH_DATA_LINEAGE_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Vector Retrieval Governance](VECTOR_RETRIEVAL_GOVERNANCE.md)

## 3. Terms and definitions

- **Property graph** — a graph model where nodes and relationships carry typed properties (label / key-value pairs).
- **RDF graph** — a graph model where statements are triples `(subject, predicate, object)` identified by IRI / literal.
- **openCypher** — the de-facto query language for property graphs, originally from Neo4j and now a vendor-neutral specification.
- **SPARQL** — the W3C-standard query language for RDF graphs.
- **Gremlin** — the Apache TinkerPop graph traversal language.
- **Index** — a data structure that accelerates graph traversals by node label, relationship type, or property.

## 4. Graph database selection

1. Neo4j is the default property-graph database for products that need mature tooling, the Graph Data Science library, and a managed option (AuraDB).
2. Amazon Neptune is preferred for products deployed on AWS that need a fully managed property-graph or RDF store with IAM-based authentication and VPC-native networking.
3. Memgraph is preferred for products that require high-throughput transactional graph workloads and dynamic graph algorithms with C++ performance characteristics.
4. The choice between property-graph and RDF is recorded in the graph database manifest; mixed deployments require a documented justification.
5. The choice is reviewed annually.

## 5. Graph schema contract

1. Every graph schema declares its node labels, relationship types, property keys, indexes, constraints, and AI risk tier.
2. Schema changes are immutable per version; breaking changes require a new schema major version and a migration plan.
3. Backwards-compatible additions (new optional properties, new node labels) are permitted under a new schema minor version.
4. Deprecated schema elements remain accessible for at least 180 days after deprecation; the deprecation date and the migration target are recorded in the manifest.

## 6. Indexing and constraints

1. Every production schema declares at least one index on the lookup property used by the most common traversal.
2. Unique constraints are enforced on natural-key properties (e.g. `(User {id})`, `(Account {id})`).
3. Existence constraints are enforced on properties that must not be null.
4. New indexes are validated against the representative query set; index bloat is monitored and remediated at least every 90 days.

## 7. Query language selection

1. openCypher is the default query language for property-graph workloads; see [Graph Query Safety & Performance Governance](GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md).
2. SPARQL is the default query language for RDF workloads that require W3C-standard semantics.
3. Gremlin is permitted for traversal-heavy workloads where openCypher / SPARQL performance is insufficient; the choice requires a documented justification.
4. Mixing query languages in a single workload requires explicit separation at the database, schema, or namespace level.

## 8. Integration with downstream subsystems

1. Graph traversals that produce feature values must follow [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md) for lineage emission.
2. Graph traversals that produce embeddings must follow [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md) for lineage emission.
3. Graph traversals that feed retrieval-augmented generation must follow [Vector Retrieval Governance](VECTOR_RETRIEVAL_GOVERNANCE.md) for retrieval safety.
4. Cross-subsystem integration is wired through the graph database manifest and validated at adoption time.

## 9. Reliability and observability

1. Workloads must declare an expected query-latency SLO and an expected availability SLO; chronic breaches trigger a schema-contract review.
2. Graph query events are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](../reference/OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
3. SLOs are defined per workload using the standard SLO template; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).
4. Dashboards and alerts are owned by the workload owner; see [Grafana Observability Platform Version Governance](../reference/GRAFANA_VERSION_GOVERNANCE.md) and [Prometheus Alerting Adoption Playbook](../playbooks/PROMETHEUS_ALERTING_ADOPTION_PLAYBOOK.md).

## 10. Security

1. TLS is required for all client, cluster, and frontend traffic.
2. Access to graphs is gated by RBAC; legacy single-user access is deprecated.
3. Personal data in nodes and relationships is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
4. Graph-query safety controls are governed by [Graph Query Safety & Performance Governance](GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md).

## 11. Operating model

1. The Graph Platform team owns the shared graph database infrastructure and the reference schema templates.
2. Workload owners own their graph schemas, queries, and runtime SLOs.
3. The Graph Platform guild meets monthly to review query latency regressions, index bloat, and adoption of new graph databases.
4. New graph database vendors are evaluated by the Graph Platform team and approved by the AI Governance Council.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
