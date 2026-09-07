# Event Schema Evolution Playbook

## Purpose

Evolve an event schema (Avro, Protobuf, JSON Schema) registered in the central Schema Registry without breaking producers or consumers. The playbook aligns with [Event Schema Governance](../standards/EVENT_SCHEMA_GOVERNANCE.md) and [Event-Streaming Platform Architecture Governance](../standards/EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md).

## Audience

Topic owners, application engineers, Schema Registry administrators, Streaming Platform engineers.

## Pre-conditions

1. The current schema is registered in the central Schema Registry with the documented compatibility level.
2. All producers and consumers of the affected subject are inventoried; backward-incompatible changes require explicit producer and consumer coordination.
3. The target schema version is reviewed by a code owner and recorded in a change ticket.
4. The staging Schema Registry is available for the rehearsal run.

## Procedure

1. **Scope the evolution.** Identify the subject, the current and target schema versions, the compatibility level, the producer and consumer set, the cutover strategy (dual-write + switch, or staged rollout), and the abort criteria. Record the plan in the change ticket.
2. **Choose the compatibility level.** Use backward compatibility for new fields added to the schema; use forward compatibility when consumers pin to a specific version; use full compatibility for bidirectional flows.
3. **Rehearse in staging.** Register the target schema in the staging Schema Registry with the chosen compatibility level; replay representative records from existing producers; replay existing records through existing consumers; verify that producers and consumers continue to function. Resolve any regression before the production run.
4. **Validate compatibility.** The Schema Registry enforces the declared compatibility level; failures are rejected by the registry. Confirm the target schema passes the registry check before promotion.
5. **Promote the target schema.** Register the target schema in the production Schema Registry with the chosen compatibility level; the registry enforces backward-incompatible rejection by default.
6. **Coordinate producer rollout.** Update producers to write with the target schema; roll out producers gradually using the platform's traffic-splitting primitives; verify produce success rate and schema-error rate.
7. **Coordinate consumer rollout.** Update consumers to read with the target schema; roll out consumers gradually using the platform's consumer-group rebalance; verify consume lag and error rate.
8. **Sign off.** Confirm that all producers and consumers have migrated to the target schema, that lag is within baseline, and that schema-error rate is zero; close the change ticket.
9. **Archive the previous schema.** After the migration window, archive the previous schema in the Schema Registry; the archive is retained for the duration mandated by the applicable regulation.

## Rollback

1. Stop the producer rollout and freeze new produce with the target schema.
2. Revert producers to the previous schema; the registry enforces producer-side rejection only at the end of the deprecation window, so a coordinated revert is required.
3. If consumers have already been updated, revert consumers to the previous schema.
4. Open a remediation ticket that captures the schema-evolution failure, the abort criterion that was triggered, and the proposed fix.
5. Communicate the rollback to stakeholders and reschedule the migration after the fix is verified.

## References

- [Event Schema Governance](../standards/EVENT_SCHEMA_GOVERNANCE.md)
- [Event-Streaming Platform Architecture Governance](../standards/EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md)
- [Event-Streaming Access Control Governance](../standards/EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md)
- [Confluent Platform Version Governance](../reference/CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md)
- [Redpanda Streaming Platform Version Governance](../reference/REDPANDA_VERSION_GOVERNANCE.md)
- [Apache Pulsar Messaging Platform Version Governance](../reference/APACHE_PULSAR_VERSION_GOVERNANCE.md)
- [Kafka KIP Version Governance](../reference/KAFKA_KIP_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Audit Event Coverage Review](AUDIT_EVENT_COVERAGE_REVIEW.md)
