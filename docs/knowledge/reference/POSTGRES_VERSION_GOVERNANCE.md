---
title: PostgreSQL Version Governance (Community, Major Versions 16/17/18)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: PostgreSQL Global Development Group; PostgreSQL documentation (https://www.postgresql.org/docs/); pgBackRest, pgAudit, pg_stat_statements documentation; PostgreSQL 16 (November 2023), 17 (September 2024), 18 (scheduled 2026-09)
---

# PostgreSQL Version Governance (Community, Major Versions 16/17/18)

## Scope

This card governs how `orchords-docs` evaluates PostgreSQL versions and the supporting tooling ecosystem. It is the reference input for any reference card that cites a relational database on top of PostgreSQL.

## Why this card exists

PostgreSQL ships a major version every 12 months. Each major brings breaking changes (e.g., `SEARCH` / `CYCLE` SQL standard syntax in 14, `MERGE` in 15, performance gains in 16, logical replication improvements in 17). Without a card binding the major version and the supporting extension matrix, the KB recommends patterns that fail on first dependency update.

## Major version support matrix

| Major | First release | EOL | Notes |
|---|---|---|---|
| 13 | November 2020 | November 2025 | LTS-style support window |
| 14 | September 2021 | November 2026 | `SEARCH`/`CYCLE` SQL standard syntax |
| 15 | October 2022 | November 2027 | `MERGE` SQL standard syntax |
| 16 | November 2023 | November 2028 | logical replication from standbys, performance |
| 17 | September 2024 | November 2029 | logical replication failover, `MERGE` improvements |
| 18 | September 2026 (planned) | November 2030 | emerging |

Policy:

- Support the current major and the previous major at any time.
- Upgrade window: ≤ 12 months after a new major release.
- Mandatory extensions documented per major.

References: `https://www.postgresql.org/support/versioning/`.

## Major-version upgrade procedure

Per PostgreSQL documentation:

1. `pg_dumpall` backup.
2. Install new version binaries.
3. `pg_upgrade --link` to perform in-place upgrade.
4. Validate schema compatibility.
5. Validate extension compatibility.
6. Run `ANALYZE` to refresh statistics.

For zero-downtime upgrades:

1. Logical replication from old to new major.
2. Cut over with read-only window.
3. Validate.
4. Decommission old.

## Logical replication

| Version | Logical replication |
|---|---|
| 10 — 13 | publication / subscription; basic |
| 14 | streaming, two-phase commit improvements |
| 15 | row filters, column lists |
| 16 | logical replication from standby |
| 17 | failover, switchover in logical replication |

References: `https://www.postgresql.org/docs/current/logical-replication.html`.

## Mandatory extension matrix

| Extension | Version | Purpose |
|---|---|---|
| `pg_stat_statements` | always | query statistics |
| `pgaudit` | always | audit logging |
| `pgBackRest` | always | backup / restore |
| `pg_cron` | optional | scheduled jobs |
| `PostGIS` | optional | spatial data |
| `pg_trgm` | optional | trigram indexing |
| `uuid-ossp` | optional | UUID generation |
| `pgcrypto` | optional | cryptographic functions |
| `hstore` | optional | key-value pairs |
| `ltree` | optional | hierarchical labels |

Policy:

- `pg_stat_statements` is required for every production deployment.
- `pgaudit` is required for every PII-bearing or regulated deployment.
- `pgBackRest` is the canonical backup tool.

## Connection security

| Setting | Required value |
|---|---|
| `ssl = on` | required |
| `ssl_protocols = 'TLSv1.2,TLSv1.3'` | required |
| `ssl_ciphers = HIGH:!aNULL:!MD5` | required |
| `ssl_cert_file` / `ssl_key_file` | required |
| `password_encryption = scram-sha-256` | required |
| `log_connections = on` | required |
| `log_disconnections = on` | required |
| `log_statement = 'ddl'` | minimum; `'mod'` for sensitive deployments |

## Authentication

| Method | Notes |
|---|---|
| `scram-sha-256` | preferred for password authentication |
| `cert` | preferred for client authentication |
| `peer` | local Unix socket only |
| `md5` | deprecated; forbidden for new deployments |
| `trust` | forbidden for production |

## Replication modes

| Mode | Use case |
|---|---|
| Streaming replication (physical) | HA, read replicas |
| Logical replication | cross-version, cross-engine, selective subset |
| Synchronous replication | zero-data-loss; latency cost |
| Asynchronous replication | default; risk of small data loss on failover |

## High availability

Policy:

- Synchronous replication to at least one replica for zero-data-loss workloads.
- Patroni or stolon as the failover orchestrator.
- Etcd, Consul, or ZooKeeper as the consensus backend.
- Validate the failover via chaos testing quarterly.

## Backup and restore

Policy:

- `pgBackRest` is the canonical backup tool.
- Backup retention: 7 daily, 4 weekly, 12 monthly.
- Backup encryption: AES-256.
- Backup target: object storage (S3-compatible) with versioning.
- Restore SLA: 1 hour for last-known-good full restore.
- Test restore quarterly.

## Mandatory pre-flight (before adopting a new PostgreSQL deployment)

1. The major version is within the support matrix.
2. Mandatory extensions are installed.
3. SSL/TLS is configured.
4. Authentication is configured per policy.
5. Replication mode is documented.
6. HA is configured.
7. Backup is configured.
8. Audit logging is configured.
9. Monitoring is wired.

## Observability

- `pg_stat_activity` connections (gauge).
- `pg_stat_statements` top queries (top N).
- `pg_stat_replication` replica lag (gauge).
- `pg_locks` lock contention (gauge).
- `pg_stat_database` txns / commits / rollbacks (counter).
- Disk usage, WAL generation, replication slot lag (per slot).

## Sources

- PostgreSQL documentation: `https://www.postgresql.org/docs/`
- PostgreSQL versioning: `https://www.postgresql.org/support/versioning/`
- pgBackRest: `https://pgbackrest.org/`
- pgAudit: `https://www.pgaudit.org/`
- Patroni: `https://patroni.readthedocs.io/`
- pg_stat_statements: `https://www.postgresql.org/docs/current/pgstatstatements.html`
