# Event-Streaming Incident Response Playbook

## Purpose

Respond to security and reliability incidents affecting event-streaming platforms (Confluent Platform, Redpanda, Apache Pulsar) and the central Schema Registry. The playbook aligns with [Event-Streaming Access Control Governance](../standards/EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md), [Event Schema Governance](../standards/EVENT_SCHEMA_GOVERNANCE.md), [Event-Streaming Platform Architecture Governance](../standards/EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md), and the standard security incident response process.

## Audience

On-call engineers, security responders, topic owners, Streaming Platform engineers.

## Pre-conditions

1. The standard incident severity levels and the on-call rotation are documented.
2. The event-streaming platform reference card is current (`CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md`, `REDPANDA_VERSION_GOVERNANCE.md`, `APACHE_PULSAR_VERSION_GOVERNANCE.md`).
3. Audit logging is enabled and routed to the central SIEM; see [Audit Event Coverage Review](AUDIT_EVENT_COVERAGE_REVIEW.md).
4. Backup and snapshot retention meet the standard requirements; see [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
5. The lag SLO alert, the EOS-regression alert, the schema-error alert, and the ACL-denial alert are wired to the on-call paging rotation.

## Procedure

1. **Detect and triage.** Identify the incident class: unauthorized read, unauthorized write, credential theft, schema injection, replay attack, tenant breach, lag SLO breach, EOS regression, or availability outage. Assign severity using the standard matrix.
2. **Contain.** Block malicious clients via ACL changes; revoke the implicated service-account credentials; freeze the affected topic via the platform's pause API; isolate the affected cluster or tenant.
3. **Eradicate.** Rotate credentials, rebuild ACLs from a known-good snapshot, and remove malicious schemas from the Schema Registry. Confirm the threat is no longer present before recovery.
4. **Recover.** Re-enable producers and consumers; restore the workload to the previous lag SLO; verify tenant scoping, schema enforcement, and EOS correctness before lifting the freeze.
5. **Communicate.** Issue stakeholder updates on the standard incident cadence; for regulated workloads, notify the AI Governance Council and the privacy officer within the SLA.
6. **Investigate.** Reconstruct the timeline from access logs, audit logs, and OTLP traces; identify the affected topics and consumers via the lineage record; quantify the exposure (tenant, record count, data class).
7. **Document.** Write the incident report with the timeline, the root cause, the affected topic manifest, the SLO that was breached, and the customer impact.
8. **Remediate.** Open remediation tickets for control gaps; update the threat model and the topic manifest; schedule the verification review.
9. **Verify.** Re-run the security review checklist and the lag regression suite before closing the incident.
10. **Learn.** Present the incident at the monthly platform guild; incorporate the lessons learned into [Event-Streaming Access Control Governance](../standards/EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md) at the next 180-day review.

## Rollback

1. If the freeze causes a workload outage, switch the workload back to the previous event source (direct API call, prior platform, or batch ingest).
2. If the rebuild fails, restore the ACL configuration from the most recent backup; document the configuration gap.
3. If the credential rotation breaks a downstream system, roll back the rotation using the break-glass procedure and re-issue scoped credentials.
4. Communicate the rollback to stakeholders via the standard incident communication channel.
5. Open a follow-up ticket to address the rollback's root cause before re-attempting recovery.

## References

- [Event-Streaming Access Control Governance](../standards/EVENT_STREAMING_ACCESS_CONTROL_GOVERNANCE.md)
- [Event Schema Governance](../standards/EVENT_SCHEMA_GOVERNANCE.md)
- [Event-Streaming Platform Architecture Governance](../standards/EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md)
- [Confluent Platform Version Governance](../reference/CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md)
- [Redpanda Streaming Platform Version Governance](../reference/REDPANDA_VERSION_GOVERNANCE.md)
- [Apache Pulsar Messaging Platform Version Governance](../reference/APACHE_PULSAR_VERSION_GOVERNANCE.md)
- [Kafka KIP Version Governance](../reference/KAFKA_KIP_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md)
- [Audit Event Coverage Review](AUDIT_EVENT_COVERAGE_REVIEW.md)
- [Audit Storage Capacity Review](AUDIT_STORAGE_CAPACITY_REVIEW.md)
- [Encryption Coverage Review](ENCRYPTION_COVERAGE_REVIEW.md)
- [Backup Coverage Review](BACKUP_COVERAGE_REVIEW.md)
