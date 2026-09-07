# Event-Streaming Platform Architecture Governance

## 1. Scope

Govern the architecture, selection, and operational use of event-streaming platforms (Confluent Platform, Redpanda, Apache Pulsar, and managed equivalents) across OrchestrAI products. Covers topic and subscription design, partitioning, retention, tiered storage, ordering and exactly-once semantics, and integration with feature, vector, and model serving subsystems.

Excludes the underlying Apache Kafka broker wire protocol, which is governed by [Kafka KIP Version Governance](../reference/KAFKA_KIP_VERSION_GOVERNANCE.md) and [Kafka Tiered Storage Governance](../reference/KAFKA_TIERED_STORAGE_GOVERNANCE.md). Excludes event schema design, which is governed by [Event Schema Governance](EVENT_SCHEMA_GOVERNANCE.md). Excludes access control, which is governed by [Event-Streaming Access Control Governance](EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md).

## 2. Normative references

- [Confluent Platform Version Governance](../reference/CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md)
- [Redpanda Streaming Platform Version Governance](../reference/REDPANDA_VERSION_GOVERNANCE.md)
- [Apache Pulsar Messaging Platform Version Governance](../reference/APACHE_PULSAR_VERSION_GOVERNANCE.md)
- [Kafka KIP Version Governance](../reference/KAFKA_KIP_VERSION_GOVERNANCE.md)
- [Kafka Tiered Storage Governance](../reference/KAFKA_TIERED_STORAGE_GOVERNANCE.md)
- [Event Schema Governance](EVENT_SCHEMA_GOVERNANCE.md)
- [Event-Streaming Access Control Governance](EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md)

## 3. Terms and definitions

- **Topic** — a named, append-only stream of records.
- **Partition** — a subdivision of a topic that allows parallel processing and ordered delivery within the partition.
- **Subscription / consumer group** — a named set of consumers that cooperatively consume the records of a topic.
- **Tiered storage** — the migration of older log segments from a primary (hot) tier to a lower-cost (cold) tier.
- **Exactly-once semantics (EOS)** — the guarantee that a record is processed exactly once by the consumer pipeline, even across retries.
- **Schema Registry** — a service that stores and validates Avro / Protobuf / JSON schemas referenced by topic records.

## 4. Event-streaming platform selection

1. Confluent Platform is preferred for products that require the commercial support tier, the Confluent connectors ecosystem, and the Schema Registry as a managed service.
2. Redpanda is preferred for products that require low-latency produce / consume, single-binary deployment, and a thread-per-core architecture.
3. Apache Pulsar is preferred for products that require multi-tenant isolation by tenant / namespace / topic, built-in geo-replication, and segmented storage.
4. The choice is recorded in the platform manifest and reviewed annually.

## 5. Topic and subscription contract

1. Every topic declares its name, version, owner, AI risk tier, partition count, retention policy, tiered-storage configuration, replication factor, ordering requirement, and EOS requirement.
2. Topic versions are immutable; breaking changes require a new topic major version (e.g. a new topic name) and a migration plan.
3. Subscription groups are declared with their consumer count, EOS requirement, and lag SLO.
4. Deprecated topics remain readable for at least 180 days after deprecation; the deprecation date and the migration target are recorded in the manifest.

## 6. Partitioning and ordering

1. Partition keys are declared in the manifest; re-partitioning a topic is permitted only with a documented migration plan.
2. Ordering is guaranteed within a partition; cross-partition ordering is not guaranteed and must be enforced by the application when required.
3. Hot-partition skew is monitored; chronic skew triggers a re-partitioning ticket.
4. Partition count is sized for the workload's throughput and parallelism targets; under-sized partitions trigger a capacity expansion ticket.

## 7. Retention and tiered storage

1. Every topic declares a retention policy expressed in time (and optionally bytes) in the manifest; default is 7 days.
2. Tiered storage is enabled for topics with retention longer than 30 days; tier migration is transparent to consumers.
3. Cold-tier cost is monitored at least every 90 days; cost anomalies trigger a remediation ticket.
4. Retention breaches (data older than the policy that is still on the hot tier) produce an alert to the workload owner.

## 8. Exactly-once semantics

1. EOS is enabled for workloads that require it; the producer idempotence flag, the transactional ID, and the consumer isolation level are recorded in the manifest.
2. EOS workloads are validated against a representative test set at adoption time and at least every 90 days.
3. EOS regressions open a remediation ticket and block promotion of any new consumer that depends on the affected topic.
4. Non-EOS workloads are explicitly documented; the absence of EOS is recorded in the manifest.

## 9. Integration with downstream subsystems

1. Streams that produce feature values must follow [Feature Pipeline Lineage Governance](FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md) for lineage emission.
2. Streams that produce embeddings must follow [Vector Embedding Lineage Governance](VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md) for lineage emission.
3. Streams consumed by regulated models must satisfy the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
4. Cross-subsystem integration is wired through the platform manifest and validated at adoption time.

## 10. Reliability and observability

1. Topics must declare an expected end-to-end latency SLO and an expected availability SLO; chronic breaches trigger a topic-contract review.
2. Producer, consumer, and broker events are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](../reference/OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
3. SLOs are defined per topic using the standard SLO template; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).
4. Dashboards and alerts are owned by the topic owner; see [Grafana Observability Platform Version Governance](../reference/GRAFANA_VERSION_GOVERNANCE.md) and [Prometheus Alerting Adoption Playbook](../playbooks/PROMETHEUS_ALERTING_ADOPTION_PLAYBOOK.md).

## 11. Security

1. TLS is required for all client and cluster traffic.
2. Access to topics is gated by RBAC; legacy single-user access is deprecated.
3. Personal data in event payloads is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
4. Access control is governed by [Event-Streaming Access Control Governance](EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md).

## 12. Operating model

1. The Streaming Platform team owns the shared event-streaming infrastructure and the reference topic templates.
2. Topic owners own their topics, partitions, retention policies, and SLAs.
3. The Streaming Platform guild meets monthly to review lag regressions, capacity, and adoption of new event-streaming platforms.
4. New event-streaming vendors are evaluated by the Streaming Platform team and approved by the AI Governance Council.

## 13. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 14. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
