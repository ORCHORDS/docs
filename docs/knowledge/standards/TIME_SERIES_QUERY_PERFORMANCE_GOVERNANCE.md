# Time-Series Query Performance Governance

## 1. Scope

Govern the query performance, indexing, caching, and cost posture of time-series databases (TimescaleDB, InfluxDB, QuestDB, and equivalents) across OrchestrAI products. Covers query language selection, indexing strategy, continuous aggregates and downsampling, query parameterization, query caching, and threat modelling for adversarial queries.

Excludes time-series schema design, which is governed by [Time-Series Database Architecture Governance](TIME_SERIES_DATABASE_ARCHITECTURE_GOVERNANCE.md). Excludes retention and compression, which is governed by [Time-Series Retention & Compression Governance](TIME_SERIES_RETENTION_COMPRESSION_GOVERNANCE.md). Excludes general query safety controls, which are governed by [Graph Query Safety & Performance Governance](GRAPH_QUERY_SAFETY_PERFORMANCE_GOVERNANCE.md) for graph databases and [API Gateway Architecture Governance](API_GATEWAY_ARCHITECTURE_GOVERNANCE.md) for API gateways.

## 2. Normative references

- [Time-Series Database Architecture Governance](TIME_SERIES_DATABASE_ARCHITECTURE_GOVERNANCE.md)
- [Time-Series Retention & Compression Governance](TIME_SERIES_RETENTION_COMPRESSION_GOVERNANCE.md)
- [TimescaleDB Time-Series Database Version Governance](../reference/TIMESCALEDB_VERSION_GOVERNANCE.md)
- [InfluxDB Time-Series Platform Version Governance](../reference/INFLUXDB_VERSION_GOVERNANCE.md)
- [QuestDB Time-Series Database Version Governance](../reference/QUESTDB_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)

## 3. Terms and definitions

- **Continuous aggregate** — a TimescaleDB materialized view that is incrementally maintained as new data arrives.
- **Downsampling task** — an InfluxDB or QuestDB scheduled operation that rolls up raw data into coarser-grained aggregates.
- **Tag index** — a database index on the tag columns that accelerates filtering by tag.
- **Query cache** — a server-side cache of compiled query plans and result sets keyed by query text and parameter values.
- **Time-range scan** — a query that scans chunks / partitions within a bounded time range.
- **Full scan** — a query that scans all chunks / partitions without a time-range filter.

## 4. Threat model

The standard threat model for time-series query workloads includes:

1. **Unbounded time-range scan (DoS)** — an attacker submits a query with no time-range filter, triggering a full scan that exhausts CPU and I/O.
2. **High-cardinality tag filter (DoS)** — an attacker submits a query that filters by a high-cardinality tag, defeating the tag index.
3. **SQL / InfluxQL / QuestDB SQL injection** — an attacker injects untrusted input into a query string, altering the query semantics.
4. **Cache poisoning** — an attacker manipulates the query cache to serve stale or attacker-controlled results.
5. **Cross-tenant query** — an attacker queries across tenant boundaries because of a missing or bypassed tenant filter.
6. **Index bypass** — an attacker crafts a query that bypasses the schema's indexes, causing a full scan.

Each threat is mapped to a control in this standard and reviewed annually.

## 5. Query parameterization

1. All untrusted input must be passed as a query parameter; string concatenation into query text is prohibited.
2. The driver must use the parameterized query API; legacy string-concatenation APIs are deprecated.
3. Parameter validation is performed at the application layer; out-of-range or malformed parameters are rejected at the access layer.
4. Query templates are reviewed for injection safety at adoption time and after every schema change.

## 6. Time-range and cardinality limits

1. Every workload declares a maximum query time range, a maximum intermediate-row count, and a maximum result-set size in the manifest.
2. The database enforces these limits via the query runtime; queries that exceed the limits are rejected with a 400 response.
3. High-cardinality tag filters are rejected at the access layer; the database enforces a maximum tag-cardinality threshold declared in the manifest.
4. Time-range and cardinality breaches produce a security event and an alert to the workload owner.

## 7. Continuous aggregates and downsampling

1. Every production query must hit a continuous aggregate or downsampled view when one is available; full scans of raw data are prohibited by default.
2. Continuous aggregates are refreshed on a schedule declared in the manifest; runtime override is prohibited without a change ticket.
3. Continuous aggregate lag is monitored; chronic lag triggers a remediation ticket.
4. Continuous aggregates are validated against the representative query set at adoption time and at least every 90 days.

## 8. Index enforcement

1. Every production query must use an index; queries that would trigger a full scan are rejected by the query planner.
2. Tag indexes are validated against the representative query set at adoption time and at least every 90 days.
3. New indexes are tested for write-amplification impact on the schema's ingest path.
4. Index bloat is monitored and remediated at least every 90 days.

## 9. Tenant isolation

1. Multi-tenant time-series tables enforce tenant scoping via a mandatory tag or row-level-security filter; queries without a tenant filter are rejected.
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
2. Personal data in time-series values is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
3. LLM-specific threats (prompt injection, retrieval leakage) are tracked under [OWASP Top 10 LLM 2025 Version Governance](OWASP_TOP_10_LLM_2025_VERSION_GOVERNANCE.md).
4. Encryption at rest is governed by [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).

## 13. Operating model

1. The Security team owns the threat model, the security review process, and the incident response process.
2. The Time-Series Platform team owns the implementation of the controls in this standard across shared infrastructure.
3. Workload owners are accountable for query parameterization, time-range limits, and tenant scoping.
4. The security and platform guilds meet jointly each quarter to review the threat model and the control coverage.

## 14. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Security owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 15. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
