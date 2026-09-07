---
title: Grafana Loki Log Aggregation System Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Grafana Loki project (grafana/loki); CNCF incubated (Graduated in 2024); documentation at grafana.com/oss/loki
---

# Grafana Loki Log Aggregation System Version Governance

## Overview

Grafana Loki is a horizontally scalable, multi-tenant log aggregation system inspired by Prometheus. It indexes only labels and stores compressed log streams as chunks or blocks, keeping cost low while integrating tightly with Grafana, Prometheus, and Promtail / Alloy. This card governs how the KB evaluates Loki versions, deployment modes, and schema transitions.

## Versioning model

Loki ships three coordinated release artifacts that must be version-pinned together:

- Helm chart: `grafana/loki` at chart version `6.x` aligned with Loki `3.x`; Helm owns the lifecycle for the distributed (microservices) deployment.
- Loki Operator: `grafana/loki-operator` (Kubernetes-native CRD-driven install); the operator's CSV / bundle version is decoupled from the Loki binary version and must be matched against the operator compatibility matrix.
- Single binary (single-binary / monolithic mode): Loki `3.x` exposes a unified `loki` binary that can run all roles in one process, intended for small clusters and quickstart deployments. Helm and operator modes remain the supported path at scale.

Minor versions follow semver; patch releases are security and bug-fix only. The KB tracks the current minor plus the previous minor (N-1) as supported.

## Component architecture

Loki can run as separate microservices or as a single binary. The named components are:

- Distributor: ingests log streams from clients (Promtail, Alloy, Docker logging driver, syslog-ng); validates, rate-limits, and shards streams by hash to ingester replicas.
- Ingester: writes in-memory log streams to backing chunks on the configured object store; flushes and hands off to long-term storage on a schedule.
- Querier: pulls chunks and blocks from the store, evaluates LogQL, and returns results; runs alongside query-frontend.
- Compactor: merges chunks into blocks, applies retention, and rewrites indexes for long-term storage (required for the chunks-to-blocks schema transition).
- Ruler: evaluates LogQL alerting and recording rules on a schedule; produces alert states for Alertmanager.
- Query-frontend: splits, parallelizes, and caches queries (split by interval, result cache via Redis / Memcached).

Ref: `https://grafana.com/docs/loki/latest/get-started/architecture/`.

## Storage backend

Loki decouples index, chunks/blocks, and ruler state from compute. Supported backends:

- Filesystem: local single-node mode only; not for production clusters.
- Amazon S3 (and S3-compatible: MinIO, Ceph RADOS Gateway).
- Google Cloud Storage (GCS).
- Azure Blob Storage.

The KB recommends object storage for any deployment beyond a single-node lab; the chunk store and the boltdb-shipper index both live on the configured object store.

## Chunks-to-blocks storage transition (v2 -> v3 schema)

Loki originally stored logs as `chunks` paired with a per-tenant BoltDB index shipped to object storage ("boltdb-shipper" mode). Loki 2.9 introduced the `tsdb` index and a new on-disk format based on TSDB blocks (the "single store" / v3 schema). Major version 3 hardened this as the default.

Migration impact:

- New deployments: use the `tsdb` (blocks) backend by default.
- Existing chunk-store deployments: run the compactor with `compactor.block-range` and the migration helper to merge chunks into blocks; verify the per-tenant index entries shift from `boltdb-shipper` to `tsdb` before decommissioning the legacy index bucket.
- Reversal: not supported once a tenant has been migrated to `tsdb`. Plan migration with the `loki-migrate` tooling and a rollback window.

## Multi-tenancy

Loki is multi-tenant by design. Every request carries an `X-Scope-OrgID` header (or equivalent auth claim) that selects the tenant ID. The querier, ingester, distributor, compactor, and ruler all enforce tenant isolation. The KB requires:

- `auth_enabled: true` in production.
- Per-tenant limits configured (`ingestion_rate_mb`, `ingestion_burst_size_mb`, `max_query_parallelism`, `retention_period`).
- One dataplane per trust boundary; do not multiplex tenants across untrusted orgs on the same cluster.

## Retention enforcement

Retention is enforced by the compactor (block-level deletion) and by per-tenant `retention_period`. For the `tsdb` backend, the compactor drops blocks past their retention horizon; the boltdb-shipper backend was deletion-on-flush. Verify:

- `compactor.retention_enabled: true`.
- `compactor.retention_table_timeout` matches the per-tenant retention period.
- `limits_config.retention_period` set per tenant (or via `retention_stream` overrides).

## Common upgrade path and schema migrations

1. Read release notes for breaking config keys (per-component `-config` flags, schema, ruler evaluation interval).
2. Upgrade Helm chart one minor at a time when crossing major boundaries.
3. For chunk-to-block migrations, enable the compactor with `compactor.compactor_working_directory` writable and `compactor.delete_request_store` configured; monitor `loki_boltdb_shipper_compactions_total` and `loki_tsdb_index_writes_total` until steady state.
4. Roll ingester, distributor, querier, and query-frontend independently; only one ingester per replica set may be unavailable at a time to preserve write availability.
5. Validate with `logcli` and a synthetic LogQL query against canary tenants before promoting.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07.

## References

- Loki docs: `https://grafana.com/docs/loki/latest/`
- Loki repo: `https://github.com/grafana/loki`
- Releases: `https://github.com/grafana/loki/releases`
- Helm chart: `https://github.com/grafana/loki/tree/main/production/helm`
- Operator: `https://github.com/grafana/loki-operator`
- Architecture: `https://grafana.com/docs/loki/latest/get-started/architecture/`
- Storage: `https://grafana.com/docs/loki/latest/storage/`
- CNCF Loki: `https://www.cncf.io/projects/loki/`
