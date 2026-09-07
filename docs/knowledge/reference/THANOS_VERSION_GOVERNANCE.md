---
title: Thanos Long-Term Prometheus Storage and HA Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Thanos project (thanos-io/thanos); CNCF incubating; documentation at thanos.io
---

# Thanos Long-Term Prometheus Storage and HA Version Governance

## Overview

Thanos extends Prometheus with unlimited, durable storage, global query, and rule evaluation by layering components on top of Prometheus's local TSDB and shipping selected data to object storage. This card governs how the KB evaluates Thanos versions, component composition, and upgrade history.

## Components

Thanos is a set of cooperating binaries; an installation typically runs several in parallel:

- Sidecar: runs alongside each Prometheus replica; uploads TSDB blocks to object storage and exposes the local engine for remote reads.
- Store: serves historical blocks from object storage; replaces the legacy `thanos compact` / `thanos store` split (Store gateway is now the unified component).
- Querier: federates queries across Store gateways and live Prometheus sidecars; deduplicates and optionally downsamples results.
- Compactor: deduplicates, downsamples (5m and 1h), and applies retention against the bucket.
- Receiver: optional ingestion endpoint that lets Thanos accept Prometheus remote-write directly, decoupling Prometheus from local storage.
- Ruler: evaluates Prometheus recording and alerting rules against Thanos data; supports rule drift migration from Prometheus rule files.

Ref: `https://thanos.io/tip/components/`.

## HA pairing with Prometheus

Thanos HA pairs two or more identically-scoped Prometheus replicas with identical external labels plus a distinct `replica=<label>`. Querier deduplicates on the other labels so duplicate series collapse to one sample per timestamp. The KB requires:

- Identical `scrape_configs` across paired replicas (rule drift creates cardinality gaps).
- Distinct, stable `replica` label; never share the `replica` value across the pair.
- Sidecar present on every replica; no half-paired deployments.

## Object storage as long-term store

Thanos stores TSDB blocks in object storage. Supported backends include S3 (and S3-compatible: MinIO, Ceph RADOS Gateway), GCS, Azure Blob, Tencent COS, and Alibaba OSS. Configuration lives under `objstore` in the Thanos configuration file (or the `objstore.config` secret in Helm). The bucket must be dedicated to Thanos; sharing a bucket with non-Thanos writers is unsupported.

## Compactor downsampling and retention

The compactor is the only component that mutates the bucket:

- Downsampling: 5-minute resolution from raw blocks after 40 hours, 1-hour resolution after 10 days.
- Retention: deletes blocks older than `--retention.resolution-raw`, `--retention.resolution-5m`, `--retention.resolution-1h`.
- Block repair: merges overlapping blocks from sidecars that raced during upload.

Operate exactly one compactor per bucket. Multiple compactors against the same bucket will corrupt the index.

## Query deduplication and downsampling

The querier exposes:

- `--query.replica-label`: the label whose distinct values identify HA replicas (typically `replica`).
- `--query.auto-downsampling`: enables 5m and 1h step queries for long-range panels.
- `--query.partial-response` / `--query.replica-label`: behavior when sources return partial results.

For Grafana datasources, set `type: Thanos`, `step_mode: auto`, and pass `max_source_resolution` so dashboards select the most efficient resolution the bucket offers.

## Ruler and rule-drift migration

Thanos Ruler evaluates rules against Thanos data and exposes its UI/API to Alertmanager. Migration from Prometheus rule files:

- Convert Prometheus rule files to Thanos Ruler format (`rule_files` on the Ruler).
- Watch for rule drift between Prometheus and Thanos Ruler during cut-over; the KB requires an empty `rule_files` on Prometheus before the Ruler becomes authoritative.
- Use `--shipper.upload-compacted` on the sidecar only if you intend to migrate the local TSDB to Thanos-managed storage.

## Upgrade path

Thanos follows semver with periodic breaking changes in `v0.x` majors. Notable breaking surfaces:

- Store gateway metadata cache: `index-cache` configuration moved from a process-local cache to a Memcached / Redis backend in `v0.31+`; older cache configs are ignored.
- Compactor deletion and downsampling: `--retention.*` flags replaced TOML-driven settings in `v0.23`; older configs log warnings then fail.
- Querier partial-response defaults: the default shifted from `abort` to `warn` in `v0.18`; operators relying on `abort` must set it explicitly.
- Receiver ingestion: `--receive.local-endpoint` and `--receive.hashring` replaced older `--receive.*` flags; review the receive config before upgrading.

General procedure:

1. Pin a specific minor (e.g. `v0.36.0`) and verify image digests against the upstream release manifest.
2. Read the release notes; flag `store gateway`, `compactor`, `querier`, and `receiver` blocks for breaking changes.
3. Roll sidecar -> store -> querier -> compactor -> ruler; the compactor must always be the last to upgrade for any given bucket.
4. Verify bucket integrity with `thanos bucket inspect` and `thanos tools bucket verify --objstore.config=...`.
5. Validate with `thanos query --endpoint=...` and a synthetic PromQL query against canary series before promotion.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07.

## References

- Thanos docs: `https://thanos.io/tip/`
- Thanos repo: `https://github.com/thanos-io/thanos`
- Releases: `https://github.com/thanos-io/thanos/releases`
- Components: `https://thanos.io/tip/components/`
- Storage: `https://thanos.io/tip/storage.md`
- Compactor: `https://thanos.io/tip/components/compact.md`
- CNCF Thanos: `https://www.cncf.io/projects/thanos/`
