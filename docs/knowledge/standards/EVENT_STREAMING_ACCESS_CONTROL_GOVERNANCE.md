# Event-Streaming Access Control Governance

## 1. Scope

Govern the authentication, authorization, audit, and tenant isolation posture of event-streaming platforms (Confluent Platform, Redpanda, Apache Pulsar, and equivalents) operated by OrchestrAI. Covers SASL / mTLS / OAuth identity, RBAC for topics, ACL for consumer groups, encryption, and incident response.

Excludes event-streaming platform architecture, which is governed by [Event-Streaming Platform Architecture Governance](EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md). Excludes event schema design, which is governed by [Event Schema Governance](EVENT_SCHEMA_GOVERNANCE.md). Excludes general database access controls, which are governed by [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).

## 2. Normative references

- [Event-Streaming Platform Architecture Governance](EVENT_STREAMING_PLATFORM_ARCHITECTURE_GOVERNANCE.md)
- [Event Schema Governance](EVENT_SCHEMA_GOVERNANCE.md)
- [Confluent Platform Version Governance](../reference/CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md)
- [Redpanda Streaming Platform Version Governance](../reference/REDPANDA_VERSION_GOVERNANCE.md)
- [Apache Pulsar Messaging Platform Version Governance](../reference/APACHE_PULSAR_VERSION_GOVERNANCE.md)
- [Kafka KIP Version Governance](../reference/KAFKA_KIP_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)
- [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **SASL** — Simple Authentication and Security Layer; the Kafka / Pulsar authentication framework.
- **mTLS** — mutual TLS where both client and server present certificates for authentication.
- **OAuth 2.0 / OIDC** — federated identity broker used for interactive users and service-to-service authentication.
- **ACL** — Access Control List; the rule that permits or denies a principal to read or write a topic.
- **RBAC** — Role-Based Access Control; the role-to-permission mapping that governs topic access.
- **Tenant scope** — a logical boundary that confines reads and writes to a single tenant (Pulsar tenant; Kafka multi-tenant cluster).

## 4. Threat model

The standard threat model for event-streaming platforms includes:

1. **Unauthorized read** — a producer or consumer reads from a topic it does not own, exposing sensitive payloads.
2. **Unauthorized write** — a producer writes to a topic it does not own, polluting downstream consumers.
3. **Credential theft** — exfiltration of SASL / OAuth / mTLS credentials, allowing an attacker to impersonate a legitimate client.
4. **Schema injection** — an attacker registers a malicious schema that bypasses validation and poisons downstream consumers.
5. **Replay attack** — an attacker captures and replays records to influence downstream state (e.g. duplicate transactions).
6. **Tenant breach** — a client writes or reads across tenant boundaries because of misconfigured ACLs.

Each threat is mapped to a control in this standard and reviewed annually.

## 5. Identity and authentication

1. All client access requires authentication; PLAINTEXT (no auth) on shared clusters is prohibited.
2. SASL/SCRAM, SASL/OAuthBearer, or mTLS is the default for service-to-service traffic.
3. OAuth 2.0 / OIDC is the default for interactive users; see [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md) for the secret-rotation pipeline.
4. Service-account credentials are scoped per workload and rotated at least every 90 days.
5. Break-glass credentials require two-person approval and produce an audit event.

## 6. Authorization and tenant scoping

1. Authorization is enforced at the broker via ACLs (Kafka) or topic policies (Pulsar); application code must not be the sole line of defense.
2. Multi-tenant clusters enforce tenant scoping via mandatory tenant / namespace / topic policy; cross-tenant access is rejected by the broker.
3. Privileged operations (topic creation, ACL modification, schema registration) require privileged credentials and produce an audit event.
4. ACL reviews are conducted at least every 90 days; over-permissive ACLs trigger a remediation ticket.

## 7. Schema Registry access control

1. Schema registration and lookup are gated by RBAC; legacy single-user access is deprecated.
2. Subject-level ACLs restrict which principals can register or read each subject.
3. Schema registration by untrusted principals is rejected; only approved producers can register new versions of a subject.
4. Schema Registry access events produce audit events; see [Event Schema Governance](EVENT_SCHEMA_GOVERNANCE.md).

## 8. Encryption

1. TLS 1.2+ is mandatory for all client and broker traffic.
2. Event payloads at rest are encrypted using envelope encryption with keys stored in the central KMS; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
3. Tiered-storage payloads inherit the encryption posture of the source cluster.
4. Personal-data payloads are encrypted with a tenant-scoped key; key rotation follows the KMS rotation policy.

## 9. Replay protection

1. EOS (exactly-once semantics) is enabled for workloads that require it; the producer idempotence flag, the transactional ID, and the consumer isolation level are recorded in the manifest.
2. Non-EOS workloads must implement deduplication at the consumer when duplicate processing would cause harm.
3. Replay attacks are detected via consumer-side deduplication or via broker-side transactional reads.
4. Replay-attack detection produces a security event and an alert to the workload owner.

## 10. Audit logging

1. All authentication attempts, authorization decisions, topic ACL changes, and schema registrations produce audit events; see [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md).
2. Audit events include `actor`, `topic`, `authn_method`, `authz_decision`, `source_ip`, and `user_agent`.
3. Audit logs are replicated to the central SIEM with retention of at least 24 months.
4. Anomaly detection alerts on unusual access patterns (sudden spike in produce errors, repeated ACL denials, schema registrations from unfamiliar IPs).

## 11. Incident response

1. Suspected unauthorized read, unauthorized write, credential theft, schema injection, replay attack, or tenant breach triggers the standard security incident response process.
2. Affected credentials are revoked within one hour of incident confirmation.
3. The incident post-mortem identifies the topic, the workload specification, and the lineage record of the affected records.
4. Post-incident actions are tracked in the remediation backlog and reviewed at the monthly platform guild.

## 12. Operating model

1. The Security team owns the threat model, the security review process, and the incident response process.
2. The Streaming Platform team owns the implementation of the controls in this standard across shared infrastructure.
3. Topic owners are accountable for topic ACLs, schema access, and downstream enforcement.
4. The security and platform guilds meet jointly each quarter to review the threat model and the control coverage.

## 13. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Security owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 14. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
