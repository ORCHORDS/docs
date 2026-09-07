# Event-Streaming Platform Adoption Playbook

## Purpose

Adopt an event-streaming platform (Confluent Platform, Redpanda, Apache Pulsar, or managed equivalent) for a new workload that requires real-time event distribution, change-data-capture, or stream processing. The playbook aligns with [Event-Streaming Platform Architecture Governance](../standards/EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md), [Event Schema Governance](../standards/EVENT_SCHEMA_GOVERNANCE.md), and [Event-Streaming Access Control Governance](../standards/EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md).

## Audience

Topic owners, Streaming Platform engineers, application engineers, security reviewers.

## Pre-conditions

1. The event-streaming platform reference card is current (`CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md`, `REDPANDA_VERSION_GOVERNANCE.md`, `APACHE_PULSAR_VERSION_GOVERNANCE.md`).
2. AI Impact Assessment is filed for the workload; see [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md).
3. Tenant scoping and data-classification decisions are documented.
4. Source and sink systems are registered in the catalogue with declared SLAs.
5. The schema format (Avro, Protobuf, JSON Schema) is selected and the central Schema Registry is available.

## Procedure

1. **Select the event-streaming platform.** Choose Confluent Platform for commercial support and the connectors ecosystem; choose Redpanda for low-latency single-binary deployment; choose Apache Pulsar for multi-tenant isolation and segmented storage.
2. **Provision the cluster.** Apply the platform Helm chart or Terraform module pinned to the supported minor; record the platform manifest in the inventory.
3. **Configure authentication and authorization.** Provision workload-scoped service-account credentials in the central secret backend; enable SASL/SCRAM, SASL/OAuthBearer, or mTLS for service-to-service traffic; enable OAuth 2.0 / OIDC for interactive users; disable PLAINTEXT authentication.
4. **Register schemas.** Register the Avro / Protobuf / JSON Schema in the central Schema Registry with the documented compatibility level; validate the schema against a representative record set.
5. **Author the topic manifests.** Declare each topic's name, version, owner, AI risk tier, partition count, retention policy, tiered-storage configuration, replication factor, ordering requirement, and EOS requirement.
6. **Configure ACLs.** Declare topic-level ACLs for producers and consumers; declare subject-level ACLs in the Schema Registry; validate ACLs against the least-privilege principle.
7. **Wire lineage.** Emit lineage records with every produce and every consume; reject records without a complete lineage record.
8. **Wire observability.** Enable Prometheus metrics, OTLP traces, lag SLO dashboards, schema-error alerts, and ACL-denial alerts following the standard observability requirements.
9. **Run a security review.** Walk through the [Event-Streaming Access Control Governance](../standards/EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md) threat model; document mitigations and residual risk; file waivers for any unmet controls.
10. **Pilot in staging.** Route 5% of production traffic to the staging cluster; compare lag, EOS correctness, and schema enforcement with the baseline.
11. **Promote to production.** Enable the production cluster; set the lag SLO alert, the EOS-regression alert, the schema-error alert, and the ACL-denial alert; hand off to the on-call rotation.
12. **Adopt the operating cadence.** Schedule the quarterly EOS regression, the annual threat-model review, the 90-day ACL review, and the 180-day standard review.

## Rollback

1. Stop the producers via the platform's pause API.
2. Switch the workload back to the previous event source (direct API call, prior platform, or batch ingest).
3. Quarantine the topic manifests for forensic review; do not delete until the security review is complete.
4. Open a remediation ticket that captures the lag regression, the EOS regression, the schema enforcement failure, or the security finding.
5. Communicate the rollback to stakeholders via the standard incident communication channel.
6. Update the workload specification with the lessons learned before the next adoption attempt.

## References

- [Event-Streaming Platform Architecture Governance](../standards/EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md)
- [Event Schema Governance](../standards/EVENT_SCHEMA_GOVERNANCE.md)
- [Event-Streaming Access Control Governance](../standards/EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md)
- [Confluent Platform Version Governance](../reference/CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md)
- [Redpanda Streaming Platform Version Governance](../reference/REDPANDA_VERSION_GOVERNANCE.md)
- [Apache Pulsar Messaging Platform Version Governance](../reference/APACHE_PULSAR_VERSION_GOVERNANCE.md)
- [Kafka KIP Version Governance](../reference/KAFKA_KIP_VERSION_GOVERNANCE.md)
- [Kafka Tiered Storage Governance](../reference/KAFKA_TIERED_STORAGE_GOVERNANCE.md)
- [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Vector Embedding Lineage Governance](../standards/VECTOR_EMBEDDING_LINEAGE_GOVERNANCE.md)
- [Feature Pipeline Lineage Governance](../standards/FEATURE_PIPELINE_LINEAGE_GOVERNANCE.md)
- [AI Model Lifecycle Management Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
