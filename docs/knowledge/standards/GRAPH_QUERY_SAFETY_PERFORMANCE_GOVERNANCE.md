# Graph Query Safety & Performance Governance

## 1. Scope

Govern the safety, performance, and cost posture of graph queries (openCypher, SPARQL, Gremlin) executed against Neo4j, Amazon Neptune, Memgraph, and equivalents across OrchestrAI products. Covers query complexity limits, traversal depth limits, query parameterization, query caching, and threat modelling for adversarial queries.

Excludes graph schema design, which is governed by [Graph Database Architecture Governance](GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md). Excludes graph data lineage, which is governed by [Graph Data Lineage Governance](GRAPH_DATA_LINEAGE_GOVERNANCE.md). Excludes API gateway query safety controls, which are governed by [API Gateway Architecture Governance](API_GATEWAY_ARCHITECTURE_GOVERNANCE.md).

## 2. Normative references

- [Graph Database Architecture Governance](GRAPH_DATABASE_ARCHITECTURE_GOVERNANCE.md)
- [Graph Data Lineage Governance](GRAPH_DATA_LINEAGE_GOVERNANCE.md)
- [Neo4j Graph Database Version Governance](../reference/NEO4J_VERSION_GOVERNANCE.md)
- [Amazon Neptune Graph Database Version Governance](../reference/NEPTUNE_VERSION_GOVERNANCE.md)
- [Memgraph In-Memory Graph Database Version Governance](../reference/MEMGRAPH_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)

## 3. Terms and definitions

- **Traversal depth** — the maximum number of relationship hops permitted in a single query.
- **Cartesian explosion** — the exponential growth of intermediate rows when joins or pattern matches span many unconstrained dimensions.
- **Query cache** — a server-side cache of compiled query plans and result sets keyed by query text and parameter values.
- **Cypher injection** — an attack that injects untrusted input into a Cypher query string.
- **Parameterized query** — a query in which untrusted inputs are bound as parameters rather than concatenated into the query text.

## 4. Threat model

The standard threat model for graph query workloads includes:

1. **Cartesian explosion (DoS)** — an attacker submits a query that triggers an exponential fan-out, exhausting CPU, memory, and storage.
2. **Long-traversal DoS** — an attacker submits a query with unbounded traversal depth, exhausting memory.
3. **Cypher / SPARQL / Gremlin injection** — an attacker injects untrusted input into a query string, altering the query semantics.
4. **Cache poisoning** — an attacker manipulates the query cache to serve stale or attacker-controlled results.
5. **Cross-tenant traversal** — an attacker queries across tenant boundaries because of a missing or bypassed tenant filter.
6. **Index bypass** — an attacker crafts a query that bypasses the schema's indexes, causing a full-graph scan.

Each threat is mapped to a control in this standard and reviewed annually.

## 5. Query parameterization

1. All untrusted input must be passed as a query parameter; string concatenation into query text is prohibited.
2. The driver must use the parameterized query API; legacy string-concatenation APIs are deprecated.
3. Parameter validation is performed at the application layer; out-of-range or malformed parameters are rejected at the access layer.
4. Query templates are reviewed for injection safety at adoption time and after every schema change.

## 6. Traversal limits

1. Every workload declares a maximum traversal depth, a maximum intermediate-row count, and a maximum result-set size in the manifest.
2. The graph database enforces these limits via the query runtime; queries that exceed the limits are rejected with a 400 response.
3. Long-traversal workloads require a documented justification and a separate SLA tier.
4. Traversal-depth breaches produce a security event and an alert to the workload owner.

## 7. Cartesian-explosion protection

1. Every query is reviewed for cartesian-explosion risk at adoption time.
2. The graph database runtime enforces intermediate-row limits per query; queries that exceed the limits are rejected.
3. Workloads that need relaxed limits require a documented justification and an elevated SLA tier.
4. Cartesian-explosion breaches produce a security event and an alert to the workload owner.

## 8. Index enforcement

1. Every production query must use an index; queries that would trigger a full-graph scan are rejected by the query planner.
2. Schema indexes are validated against the representative query set at adoption time and at least every 90 days.
3. New indexes are tested for write-amplification impact on the schema's ingest path.
4. Index bloat is monitored and remediated at least every 90 days.

## 9. Tenant isolation

1. Multi-tenant graphs enforce tenant scoping via a mandatory node label or relationship filter; queries without a tenant filter are rejected.
2. Cross-tenant queries are prohibited; the access layer rejects any query whose tenant filter does not match the caller's identity.
3. Tenant boundaries are audited quarterly; see [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md).
4. Cross-tenant breaches produce a security incident.

## 10. Query cache

1. The query cache is enabled for all production databases; cache hit rate is monitored.
2. The cache is keyed by query text and parameter values; parameter hashing prevents cache poisoning via parameter substitution.
3. Cache entries are invalidated on schema change.
4. Cache poisoning attempts produce a security event.

## 11. Performance and reliability

1. Workloads must declare an expected query-latency SLO and an expected availability SLO; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).
2. Slow-query logs are sampled and reviewed weekly; chronic slow queries trigger a query-tuning ticket.
3. Query plans are reviewed for regression at least every 90 days; plan regressions trigger a remediation ticket.
4. New queries must be reviewed for safety and performance at adoption time.

## 12. Security

1. TLS 1.2+ is required for all client and cluster traffic.
2. Personal data in nodes and relationships is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
3. LLM-specific threats (prompt injection, retrieval leakage) are tracked under [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md).
4. Encryption at rest is governed by [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).

## 13. Operating model

1. The Security team owns the threat model, the security review process, and the incident response process.
2. The Graph Platform team owns the implementation of the controls in this standard across shared infrastructure.
3. Workload owners are accountable for query parameterization, traversal limits, and tenant scoping.
4. The security and platform guilds meet jointly each quarter to review the threat model and the control coverage.

## 14. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Security owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 15. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
