---
title: Confluent Platform Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://docs.confluent.io/platform/current/release-notes/index.html
---

# Confluent Platform Version Governance

## Why this card exists

Confluent Platform is the commercial distribution of Apache Kafka plus a curated set of connectors, schema registry, ksqlDB, and control-center tooling. ConfestrAI uses Confluent Platform for products that require the commercial support tier, Confluent's connectors ecosystem, and the Schema Registry as a managed service. Confluent releases bundle the Apache Kafka broker with Confluent-internal components on independent cadences; each platform release ships breaking changes in the Schema Registry API, ksqlDB grammar, and Connect connector contract. This card defines how OrchestrAI selects, upgrades, and retires Confluent Platform versions across self-hosted clusters and Confluent Cloud.

## Scope

Applies to Confluent Platform (self-hosted), Confluent Cloud, Confluent Schema Registry, ksqlDB, Confluent Connect, and the Confluent REST Proxy. Excludes the underlying Apache Kafka broker, which is governed by [Kafka KIP Version Governance](KAFKA_KIP_VERSION_GOVERNANCE.md) and [Kafka Tiered Storage Governance](KAFKA_TIERED_STORAGE_GOVERNANCE.md).

## Versioning model

Confluent Platform follows `<major>.<minor>` for the platform bundle and `<major>.<minor>.<patch>` for individual components:

- **Platform major** — incompatible broker protocol, breaking Schema Registry API contract, or removal of a supported component.
- **Platform minor** — backward-compatible feature additions (new connectors, new ksqlDB functions, new Schema Registry features); broker protocol is forward-readable by the next major.
- **Component patch** — bug fixes, security patches, performance backports; no API change.

## Supported versions

| Platform version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 8.0.x | Primary | 2027-06 | Default for new clusters; introduces the new Schema Registry v2 API and ksqlDB improvements. |
| 7.9.x | Maintenance | 2026-12 | Receives security patches; recommended upgrade path. |
| 7.6.x | End of life | 2026-06 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 7.6 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to the latest stable platform minor (currently 8.0.x).
2. The pin is recorded in the platform manifest and validated by the platform reconciliation loop.
3. Confluent Cloud subscriptions default to the latest dedicated cluster tier.

## Upgrade cadence

- **Component patch** — applied within 14 days of upstream release.
- **Platform minor** — applied within 90 days, after running the cross-version Schema Registry / ksqlDB regression suite.
- **Platform major** — applied within 180 days; gated by a staging rehearsal that exercises broker upgrade, Schema Registry migration, and Connect plugin upgrade.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date Confluent announces end of support.
2. Clusters on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new topics cannot be created on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| Apache Kafka broker | matches platform minor | See [Kafka KIP Version Governance](KAFKA_KIP_VERSION_GOVERNANCE.md). |
| Schema Registry | matches platform minor | Pinned via Confluent CLI. |
| ksqlDB | matches platform minor | Pinned via Confluent CLI. |
| Confluent Connect | matches platform minor | Plugin contract declared per connector. |
| Confluent REST Proxy | matches platform minor | HTTP ingress for Kafka clients. |
| Confluent Control Center | matches platform minor | Optional UI for cluster management. |

## Security and compliance

- TLS 1.2+ is mandatory for all client, broker, and Schema Registry traffic.
- SASL/SCRAM or mTLS authentication is required for all clients; legacy PLAINTEXT authentication on shared clusters is prohibited.
- Schema Registry enforces schema validation on every produce request; backward-incompatible schema evolution is rejected by default.
- Audit logging is wired through the standard log pipeline; topic-level audit events must include `topic`, `actor`, `operation`, and `schema_id`.
- Personal data in event payloads is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the broker metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Producer and consumer traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for broker lag, partition health, and Schema Registry error rate live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Redpanda Streaming Platform Version Governance](REDPANDA_VERSION_GOVERNANCE.md)
- [Apache Pulsar Messaging Platform Version Governance](APACHE_PULSAR_VERSION_GOVERNANCE.md)
- [Kafka KIP Version Governance](KAFKA_KIP_VERSION_GOVERNANCE.md)
- [Kafka Tiered Storage Governance](KAFKA_TIERED_STORAGE_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
