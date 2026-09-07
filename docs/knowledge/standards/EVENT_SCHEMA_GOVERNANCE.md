# Event Schema Governance

## 1. Scope

Govern the schema lifecycle for event-streaming topics (Confluent Platform, Redpanda, Apache Pulsar, and equivalents) across OrchestrAI products. Covers schema format selection (Avro, Protobuf, JSON Schema), schema registration, compatibility checks, schema evolution, and deprecation.

Excludes event-streaming platform architecture, which is governed by [Event-Streaming Platform Architecture Governance](EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md). Excludes access control, which is governed by [Event-Streaming Access Control Governance](EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md). Excludes the underlying Apache Kafka wire protocol, which is governed by [Kafka KIP Version Governance](../reference/KAFKA_KIP_VERSION_GOVERNANCE.md).

## 2. Normative references

- [Event-Streaming Platform Architecture Governance](EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md)
- [Event-Streaming Access Control Governance](EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md)
- [Confluent Platform Version Governance](../reference/CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md)
- [Redpanda Streaming Platform Version Governance](../reference/REDPANDA_VERSION_GOVERNANCE.md)
- [Apache Pulsar Messaging Platform Version Governance](../reference/APACHE_PULSAR_VERSION_GOVERNANCE.md)
- [Kafka KIP Version Governance](../reference/KAFKA_KIP_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Schema** — a structured description of the data carried by an event-streaming record.
- **Schema Registry** — a service that stores, versions, and validates schemas referenced by topic records.
- **Compatibility level** — the rule that determines which schema changes are permitted (backward, forward, full, none, transitive).
- **Backward compatibility** — a new schema can read data written with the previous schema.
- **Forward compatibility** — the previous schema can read data written with the new schema.
- **Schema evolution** — the controlled change of a schema over time, governed by the compatibility level.

## 4. Schema format selection

1. Avro is the default schema format for new topics; it provides compact binary encoding and a rich schema evolution model.
2. Protobuf is preferred for topics that integrate with Google ecosystem clients or that require cross-language interop with a strong schema.
3. JSON Schema is permitted only for topics that integrate with browser-based producers that cannot run a code-generated encoder.
4. Schema-less topics are prohibited for production workloads; legacy schema-less topics must be migrated within 180 days.

## 5. Schema registration

1. Every production schema is registered in the central Schema Registry before the topic is enabled for produce.
2. Schema registration is gated by a code review and a documented change ticket; the registry stores the schema content hash, the version, the owner, and the compatibility level.
3. Subject naming follows the documented convention (`<topic>-value` or `<topic>-key`); deviations are recorded in the manifest with justification.
4. Schemas without an active owner are flagged at least every 90 days and assigned a new owner or deprecated.

## 6. Compatibility levels

1. Backward compatibility is the default compatibility level for new topics; new schemas can read data written with the previous schema.
2. Forward compatibility is permitted for topics consumed by external clients that pin to a specific schema version.
3. Full compatibility is required for topics that flow bidirectionally between two services.
4. Compatibility level changes are recorded in the manifest and require a code review.

## 7. Schema evolution

1. Schema changes are submitted to the Schema Registry with a documented change ticket; the registry enforces the declared compatibility level.
2. Backward-incompatible changes are rejected by the registry by default; a documented override is required to bypass the rejection.
3. Transitive compatibility is required for topics that have many historical versions; the registry validates the full version chain.
4. New schema versions are validated against a representative record set at adoption time; rejections open a remediation ticket.

## 8. Schema deprecation

1. Deprecated schemas remain readable for at least 180 days after deprecation; the deprecation date and the migration target are recorded in the manifest.
2. Producers must migrate to the new schema within the deprecation window; the registry enforces producer-side rejection at the end of the window.
3. Consumers may continue to read with the deprecated schema after the producer migration; consumer-side rejection is enforced when all consumers have migrated.
4. Deprecated schemas are archived in the Schema Registry; the archive is retained for the duration mandated by the applicable regulation.

## 9. Provenance and audit

1. Every schema registration produces an audit event that includes `subject`, `version`, `owner`, `change_ticket`, and `compatibility_level`.
2. Every schema lookup produces an audit event that includes `subject`, `version`, `actor`, and `consumer_application`.
3. Audit events are replicated to the central audit pipeline; see [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md).
4. Audit retention is at least 24 months.

## 10. Security

1. TLS 1.2+ is required for all client and Schema Registry traffic.
2. Access to schema registration and lookup is gated by RBAC; legacy single-user access is deprecated.
3. Personal data in schema fields is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
4. Encryption at rest is governed by [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).

## 11. Operating model

1. The Streaming Platform team owns the central Schema Registry and the reference schema templates.
2. Topic owners own their schemas, compatibility levels, and evolution plans.
3. The Streaming Platform guild meets monthly to review schema regressions and adoption of new schema features.
4. New schema formats are evaluated by the Streaming Platform team and approved by the AI Governance Council.

## 12. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the AI Governance Council chair. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 13. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
