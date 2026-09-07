---
title: Apache Kafka Tiered Storage Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://kafka.apache.org/documentation ; https://github.com/apache/kafka
---

# Apache Kafka Tiered Storage Version Governance

## 1. Purpose

This reference card defines the version-governance model for Apache Kafka's **Tiered Storage** feature (KIP-405, GA in 3.6) which offloads older log segments from local broker storage to remote object storage (S3, GCS, Azure Blob, or HDFS). It applies to self-managed Kafka clusters and to Kafka-compatible systems (Redpanda, MSK, Confluent Cloud) that expose a Tiered Storage toggle.

## 2. Scope

In scope:

- Apache Kafka ≥ 3.6 with Tiered Storage enabled.
- Remote storage manager (RSM) implementations: `S3RemoteStorageManager`, `GcsRemoteStorageManager`, `AzureBlobRemoteStorageManager`, `HdfsRemoteStorageManager`.
- Local log retention reduced to the **hot tier** (configurable per-topic).
- KRaft-based cluster (KIP-500) — Tiered Storage is unsupported on legacy ZK clusters.

Out of scope:

- Custom object-store backends without a Kafka-shipped RSM.
- Tiered Storage in non-Kafka brokers unless explicitly compatible (e.g. Redpanda Tiered Storage).

## 3. Versioning policy

- Pin Kafka to a specific patch release (e.g. `3.7.2`) and SHA-512 digest; never float on `:latest`.
- Tiered Storage is **GA only from 3.6**; do not enable on 3.5 or earlier even if KIP-405 is feature-flagged.
- KRaft mode is mandatory: ZK clusters cannot enable Tiered Storage.
- Local log retention should be reduced to a few hours (typical 6-24 h); the rest is fetched on demand from remote storage.

## 4. Compatibility matrix

| Kafka | KRaft | Tiered Storage | Notes |
| --- | --- | --- | --- |
| 3.5.x | opt-in | preview (off by default) | Not for production |
| 3.6.x | default | GA | S3 and GCS RSM |
| 3.7.x | default | GA | Azure Blob RSM, HDFS RSM improvements |
| 3.8.x | default | GA | Server-side fetch batching, S3 Express One Zone |

## 5. Configuration

- Enable per-topic or per-broker: `remote.storage.enable=true` (broker), `remote.storage.manager.class.name=...` (broker), `local.retention.ms=21600000` (topic).
- Use IAM role or workload identity federation for cloud object-store credentials; never use static long-lived keys.
- Set `remote.fetch.max.bytes` ≤ 16 MiB to bound per-fetch memory cost.

## 6. Capacity planning

- Calculate local disk size based on aggregate topic throughput × local retention (not on log.retention.ms).
- Estimate remote storage growth as `aggregate_throughput × retention_window` minus `local.retention`.
- Provision object-store with at least 50% headroom; tiered storage does not replace backup.

## 7. Upgrade procedure

1. Upgrade brokers to the target version with Tiered Storage **disabled**.
2. Validate cluster health, then enable `remote.storage.enable=true` broker by broker (one at a time).
3. After one full ISR cycle, reduce `local.retention.ms` topic-by-topic and observe fetch latency.

## 8. Rollback procedure

- Set `local.retention.ms` back to the pre-Tiered-Storage value; existing local log segments remain on disk.
- Disable `remote.storage.enable` on one broker at a time. No data loss as long as object-store contents are preserved for the original retention window.

## 9. Observability

- Required metrics: `kafka_server_remote_fetch_total{result}`, `kafka_log_remote_log_size_bytes`, `kafka_server_remote_copy_bytes_total`, `kafka_log_log_start_offset`.
- Alert on `rate(kafka_server_remote_fetch_total{result="error"}[5m]) > 0.01` and on `kafka_log_remote_log_size_bytes > bucket_quota`.

## 10. References

- KIP-405 — Tiered Storage — https://cwiki.apache.org/confluence/display/KAFKA/KIP-405%3A+Tiered+Storage
- Apache Kafka documentation — https://kafka.apache.org/documentation/
