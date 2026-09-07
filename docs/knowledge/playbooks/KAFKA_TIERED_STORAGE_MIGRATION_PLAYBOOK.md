# Kafka Tiered Storage Migration Playbook

## Purpose

Migrate an Apache Kafka 3.6+ cluster to enable Tiered Storage (KIP-405) without consumer-visible downtime, with a rollback path that preserves on-disk data.

## Audience

Data platform engineers, SRE on-call, application owners with topics on the affected cluster.

## Pre-conditions

- Apache Kafka ≥ 3.6 with KRaft mode (mandatory).
- S3-compatible or GCS/Azure Blob object store with IAM role-based access configured (no static keys).
- Local broker disk sized for at least one full ISR cycle of headroom during migration.
- A canary topic with synthetic producer/consumer for behavioural diff.

## Procedure

1. **Pre-flight**: capture baseline metrics — `kafka_log_log_size`, `kafka_server_fetch_total`, end-to-end consumer lag.
2. **Broker upgrade**: roll all brokers to the target Kafka version with `remote.storage.enable=false`. Verify cluster health with `kafka-broker-api-versions.sh` and the Kafka KRaft admin API.
3. **Enable Tiered Storage broker-wide**: set `remote.storage.enable=true`, `remote.storage.manager.class.name=org.apache.kafka.server.log.remote.storage.S3RemoteStorageManager` (or equivalent RSM), restart brokers one at a time.
4. **Migrate a canary topic**: set `local.retention.ms=3600000` (1 hour) on the canary topic only; observe that older segments are offloaded and that fetch-from-remote works correctly (`kafka.server.remote.fetch.total{result="success"}`).
5. **Consumer parity**: replay the canary consumer against offsets spanning the offload window; verify zero duplicate, zero loss, and message-by-message equality.
6. **Roll cluster-wide**: lower `local.retention.ms` on each production topic over several days, starting with the lowest-throughput topics.
7. **Observability guardrails**: configure SLOs on `kafka_server_remote_fetch_total{result="error"} < 0.5%` and on consumer lag < 2× pre-migration baseline.
8. **Document**: update the runbook with the bucket name, IAM role, and `local.retention.ms` per topic; link from `policies/tiered-storage/`.

## Rollback

- Restore `local.retention.ms` to its previous value (e.g. 7 days). Existing remote-tier data continues to be ignored because the broker can satisfy fetches from local.
- Disable `remote.storage.enable` broker by broker. No data loss; remote-tier artefacts can be retained or deleted per retention policy.

## References

- KIP-405 — Tiered Storage — https://cwiki.apache.org/confluence/display/KAFKA/KIP-405%3A+Tiered+Storage
- Internal: Batch 99 reference card `KAFKA_TIERED_STORAGE_GOVERNANCE.md`.
