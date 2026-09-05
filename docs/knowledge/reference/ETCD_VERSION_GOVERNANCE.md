---
title: etcd Version Governance (CNCF, distributed KV store)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: etcd project (https://etcd.io/), CNCF; etcd 3.4 / 3.5 series; CNCF Graduation announcement (2018); Kubernetes integration; etcd-operator documentation
---

# etcd Version Governance (CNCF, distributed KV store)

## Scope

This card governs how `orchords-docs` evaluates etcd versions and the supporting ecosystem. etcd is the canonical distributed key-value store used by Kubernetes (kube-apiserver), Patroni (PostgreSQL HA), Consul (alternate backend), and many distributed systems.

## Why this card exists

etcd is a critical-path component for many cluster managers (especially Kubernetes control plane). Each etcd release brings new APIs, deprecations, and cluster-membership semantics. A KB card that recommends "etcd" without binding to the version, cluster size, and backup procedure produces a configuration that breaks on first dependency update.

## Version support matrix

| Series | Status | Notes |
|---|---|---|
| 3.4.x | stable | Kubernetes 1.22 — 1.28 compatible |
| 3.5.x | stable | Kubernetes 1.25+ compatible; performance and security improvements |
| 3.6.x | alpha (2026-09) | in development |

Policy:

- Production: 3.5.x is preferred.
- 3.4.x supported for legacy clusters.
- 3.6.x experimental.

References: `https://etcd.io/docs/`.

## Cluster size and quorum

- Recommended cluster size: 3 or 5 nodes.
- 3 nodes: tolerates 1 failure (quorum = 2).
- 5 nodes: tolerates 2 failures (quorum = 3).
- Avoid even-numbered clusters.
- Do not run more than 7 nodes (consensus performance degrades).

## Storage backend

| Backend | Default |
|---|---|
| bbolt (BoltDB) | default since 3.4 |
| Memory (not persistent) | not for production |

Policy:

- bbolt is required for production.
- `--quota-backend-bytes` enforces a backend size limit.
- Defragmentation is needed after large key deletes (`etcdctl defrag`).

## TLS and authentication

| Setting | Required |
|---|---|
| `--cert-file` / `--key-file` (server) | required |
| `--trusted-ca-file` (server) | required |
| `--client-cert-auth` | required |
| `--peer-cert-file` / `--peer-key-file` | required |
| `--peer-trusted-ca-file` | required |
| `--initial-cluster` (bootstrap) | required |
| Authentication (RBAC) | required since 3.3 |
| Encryption-at-rest | recommended |

## Backup and restore

| Tool | Purpose |
|---|---|
| `etcdctl snapshot save` | backup |
| `etcdctl snapshot restore` | restore |
| `etcdctl snapshot status` | validate |
| Velero | Kubernetes-aware backup |
| etcd-operator | operator-level backup |

Policy:

- Snapshot every 4 hours (default) or 15 minutes for high-velocity workloads.
- Snapshot retention: 30 days.
- Snapshot encryption: AES-256.
- Snapshot target: object storage (S3-compatible).
- Test restore quarterly.

## Watch and lease

- Watch is the change-notification primitive; supports cancellation.
- Lease is the time-bounded key primitive (TTL).
- Lease IDs are tied to a key for liveness checks.

## Mandatory pre-flight (before adopting a new etcd deployment)

1. Version is within the support matrix.
2. Cluster size follows the quorum policy.
3. TLS / authentication is configured.
4. Backup / restore procedure is documented.
5. Monitoring is wired.

## Cross-reference

| Domain | Card |
|---|---|
| Kubernetes | (deferred) |
| PostgreSQL HA | `POSTGRES_VERSION_GOVERNANCE.md` |
| Consul | (deferred) |
| Kafka KRaft | `KAFKA_KIP_VERSION_GOVERNANCE.md` |

## Observability

- `etcd_server_has_leader` (gauge: 1/0).
- `etcd_server_leader_changes_seen_total` (counter).
- `etcd_server_proposals_committed_total` (counter).
- `etcd_server_proposals_pending` (gauge).
- `etcd_server_proposals_failed_total` (counter).
- `etcd_disk_backend_commit_duration_seconds` (histogram).
- `etcd_network_peer_round_trip_time_seconds` (histogram).
- `etcd_server_health` (gauge).

## Sources

- etcd documentation: `https://etcd.io/docs/`
- etcd GitHub: `https://github.com/etcd-io/etcd`
- CNCF etcd project: `https://www.cncf.io/projects/etcd/`
- etcd-operator: `https://github.com/etcd-io/etcd-operator`
- etcd benchmarks: `https://etcd.io/docs/performance/`
