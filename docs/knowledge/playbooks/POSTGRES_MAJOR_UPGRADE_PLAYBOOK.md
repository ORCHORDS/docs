# PostgreSQL Major Version Upgrade Playbook

## Purpose

Drive a PostgreSQL major version upgrade (e.g., 16 → 17, 17 → 18) end-to-end with predictable rollback. The playbook covers in-place upgrades via `pg_upgrade`, zero-downtime upgrades via logical replication, and pre-flight validation.

## Audience

Database administrators, SRE on-call, application owners, platform team.

## Pre-conditions

1. The reference card is current: `POSTGRES_VERSION_GOVERNANCE.md`.
2. The target version is within the supported matrix.
3. A staging cluster mirrors production topology (size, extensions, queries).
4. `pgBackRest` backup is current.
5. The change ticket is open with the upgrade window.
6. Application owners have signed off on the upgrade.

## Procedure

### 1. Pre-flight

1. Confirm the target major version is supported for ≥ 12 months.
2. Read the release notes for the target version; identify breaking changes.
3. Audit the extension matrix: confirm every extension supports the target version.
4. Audit deprecated APIs: `SELECT * FROM pg_catalog.pg_extension`; confirm no deprecated extension.
5. Audit stored procedures: confirm no use of deprecated functions.
6. Audit custom data types: confirm type compatibility.
7. Run `pg_upgrade --check` against staging.

### 2. In-place upgrade (`pg_upgrade`)

1. Take a final `pgBackRest` backup of the old cluster.
2. Stop the application.
3. Stop PostgreSQL on the old version.
4. Initialize the new cluster (`initdb`).
5. Run `pg_upgrade --link --old-datadir <old> --new-datadir <new> --old-bindir <old_bin> --new-bindir <new_bin>`.
6. Update PostgreSQL binaries (link the new binaries; archive the old).
7. Start PostgreSQL on the new version.
8. Run `ANALYZE` to refresh statistics.
9. Run the application's smoke test.
10. Validate vacuum, autovacuum, and replication.

### 3. Zero-downtime upgrade (logical replication)

1. Initialize a new PostgreSQL cluster at the target version.
2. On the old cluster: `CREATE PUBLICATION pub_for_upgrade FOR ALL TABLES`.
3. On the new cluster: `CREATE SUBSCRIPTION sub_for_upgrade CONNECTION '...' PUBLICATION pub_for_upgrade`.
4. Wait for initial sync to complete.
5. On the new cluster: monitor replication lag.
6. Cut over:
   - Stop the application writes.
   - Wait for the new cluster to catch up.
   - Promote the new cluster (`pg_promote()`).
   - Update the application's connection string.
   - Restart the application.
7. Validate behavior.
8. Decommission the old cluster.

### 4. Validation

- Connection rate: ≥ baseline.
- Query latency p99: ≤ baseline + 10%.
- Replication lag: ≤ 1 second.
- Backup / restore smoke test: pass.
- Audit log: every query category is logged.

### 5. Rollback

In-place upgrade rollback:

1. Stop the new cluster.
2. Restore the old binaries.
3. Start the old cluster.
4. Validate.
5. Replay the change ticket as failed.

Zero-downtime upgrade rollback:

1. Stop the new cluster.
2. Resume the old cluster.
3. Update the application's connection string back.
4. Validate.

## Mandatory pre-flight (before a major version upgrade)

1. Reference card is current.
2. Target version is supported.
3. Staging cluster passes `pg_upgrade --check`.
4. Backup is current.
5. Application owners sign off.
6. Rollback procedure is documented.

## Mandatory post-flight

1. Old binaries are archived (≥ 7 days; not deleted).
2. `pg_stat_statements` is current.
3. Backup continues with the new version.
4. Replication is re-established.
5. Documentation is updated.

## References

- `POSTGRES_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- pg_upgrade documentation: `https://www.postgresql.org/docs/current/pgupgrade.html`
- Logical replication documentation: `https://www.postgresql.org/docs/current/logical-replication.html`
- pgBackRest: `https://pgbackrest.org/`
