---
title: Redpanda Streaming Platform Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/redpanda-data/redpanda/releases
---

# Redpanda Streaming Platform Version Governance

## Why this card exists

Redpanda is the C++ implemented, Kafka-compatible streaming platform used by OrchestrAI products that require low-latency produce / consume, single-binary deployment, and a thread-per-core architecture that avoids JVM tail-latency behaviour. Redpanda releases bundle the broker, the Schema Registry, the HTTP Proxy (PandaProxy), and the Console frontend on independent cadences. Each major version ships breaking changes in the Admin API, the configuration schema, and the tiered-storage contract. This card defines how OrchestrAI selects, upgrades, and retires Redpanda versions across self-hosted clusters and Redpanda Cloud.

## Scope

Applies to Redpanda (self-hosted), Redpanda Cloud, Redpanda Schema Registry, Redpanda Connect (formerly Benthos), and the Redpanda Console. Excludes the upstream Apache Kafka wire protocol, which is governed by [Kafka KIP Version Governance](KAFKA_KIP_VERSION_GOVERNANCE.md) for protocol compatibility.

## Versioning model

Redpanda follows `<major>.<minor>.<patch>`:

- **Major** — incompatible Admin API, breaking configuration schema, removal of a supported feature flag, or breaking tiered-storage contract.
- **Minor** — backward-compatible feature additions (new Admin API endpoints, new configuration options, new tiered-storage improvements); configuration schema is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 24.3.x | Primary | 2027-03 | Default for new clusters; introduces the new tiered-storage improvements and the new Redpanda Connect GA. |
| 24.2.x | Maintenance | 2026-09 | Receives security patches; recommended upgrade path. |
| 24.1.x | End of life | 2026-03 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 24.1 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to the latest stable minor in the 24.3.x line.
2. The pin is recorded in the platform manifest and validated by the platform reconciliation loop.
3. Pre-release builds (`-rc.N`) are restricted to evaluation clusters and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version Kafka-protocol regression suite and the Admin API migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises tiered-storage migration, schema registry upgrade, and HTTP proxy migration.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Clusters on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new topics cannot be created on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| Kafka wire protocol | 2.5+ | Backward-compatible with the upstream Apache Kafka wire protocol. |
| Redpanda Schema Registry | matches server minor | Compatible with the Confluent Schema Registry wire protocol. |
| Redpanda Connect | latest minor | Plugin contract declared per connector. |
| Redpanda Console | latest minor | UI for cluster management. |
| rpk CLI | matches server minor | Operational CLI. |

## Security and compliance

- TLS 1.2+ is mandatory for all client and cluster traffic.
- SASL/SCRAM or mTLS authentication is required for all clients; legacy PLAINTEXT authentication on shared clusters is prohibited.
- Schema Registry enforces schema validation on every produce request; backward-incompatible schema evolution is rejected by default.
- Audit logging is wired through the standard log pipeline; topic-level audit events must include `topic`, `actor`, `operation`, and `schema_id`.
- Personal data in event payloads is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the broker metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Producer and consumer traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for broker lag, partition health, and tiered-storage traffic live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Confluent Platform Version Governance](CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md)
- [Apache Pulsar Messaging Platform Version Governance](APACHE_PULSAR_VERSION_GOVERNANCE.md)
- [Kafka KIP Version Governance](KAFKA_KIP_VERSION_GOVERNANCE.md)
- [Kafka Tiered Storage Governance](KAFKA_TIERED_STORAGE_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
