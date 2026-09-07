---
title: Apache Pulsar Messaging Platform Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/apache/pulsar/releases
---

# Apache Pulsar Messaging Platform Version Governance

## Why this card exists

Apache Pulsar is the cloud-native, segmented messaging and streaming platform used by OrchestrAI products that require tiered storage between BookKeeper and long-term object storage, multi-tenant isolation by tenant / namespace / topic, and built-in geo-replication. Pulsar releases combine the broker, the BookKeeper bookies, the ZooKeeper / metadata store, and the function worker on independent cadences. Each major version ships breaking changes in the topic lookup protocol, the function worker contract, and the tiered-storage configuration. This card defines how OrchestrAI selects, upgrades, and retires Pulsar versions across self-hosted clusters, StreamNative Cloud, and Apache Pulsar Operators on Kubernetes.

## Scope

Applies to Apache Pulsar (self-hosted), StreamNative Cloud, Apache Pulsar Operators (Helm / OperatorHub), the Pulsar Functions / IO worker, and the Pulsar SQL / Presto integration. Excludes Apache BookKeeper and Apache ZooKeeper, which are governed by their own cards.

## Versioning model

Pulsar follows `<major>.<minor>.<patch>`:

- **Major** — incompatible topic lookup protocol, breaking function worker contract, or removal of a supported feature flag.
- **Minor** — backward-compatible feature additions (new topic policies, new function triggers, new tiered-storage improvements); topic lookup protocol is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 4.0.x | Primary | 2027-03 | Default for new clusters; introduces the new metadata-store contract and the new Functions v4 API. |
| 3.3.x | Maintenance | 2026-09 | Receives security patches; recommended upgrade path. |
| 3.2.x | End of life | 2026-03 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 3.2 | End of life | — | Not permitted in production. |

## Selection criteria

1. New clusters default to the latest stable minor in the 4.0.x line.
2. The pin is recorded in the platform manifest and validated by the platform reconciliation loop.
3. Pre-release builds are restricted to evaluation clusters and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version topic-policy regression suite and the function worker migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises tiered-storage migration, function worker upgrade, and metadata-store migration.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Clusters on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new tenants cannot be created on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| Apache BookKeeper | 4.16.x, 4.17.x | Required for the bookies. |
| Apache ZooKeeper | 3.8.x, 3.9.x | Required for the metadata store; or use the new metadata-store contract. |
| Pulsar Functions / IO | matches server minor | Pinned via package manager. |
| Pulsar SQL (Trino) | 432+ | Required for the SQL interface. |
| Pulsar Admin API | matches server minor | Used for cluster management. |
| StreamNative Cloud | managed | Vendor-managed; SLA applies. |

## Security and compliance

- TLS 1.2+ is mandatory for all client, broker, and bookie traffic.
- OAuth 2.0 / OIDC or mTLS authentication is required for all clients; legacy PLAINTEXT authentication on shared clusters is prohibited.
- Multi-tenant isolation is enforced at the tenant / namespace / topic level via the standard topic policies.
- Audit logging is wired through the standard log pipeline; topic-level audit events must include `tenant`, `namespace`, `topic`, `actor`, `operation`, and `subscription`.
- Personal data in event payloads is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on the broker metrics endpoint; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Producer and consumer traces are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for broker lag, bookie health, and tiered-storage traffic live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Confluent Platform Version Governance](CONFLUENT_PLATFORM_VERSION_GOVERNANCE.md)
- [Redpanda Streaming Platform Version Governance](REDPANDA_VERSION_GOVERNANCE.md)
- [Kafka KIP Version Governance](KAFKA_KIP_VERSION_GOVERNANCE.md)
- [Kafka Tiered Storage Governance](KAFKA_TIERED_STORAGE_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
