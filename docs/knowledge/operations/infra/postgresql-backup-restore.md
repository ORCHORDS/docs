# postgresql-backup-restore

**Issue:** Reliable PostgreSQL backup strategies and tested restore procedures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
pg_dump backups are taken but never tested for restore. WAL archiving is not configured, making point-in-time recovery impossible. Large databases take hours to restore from a logical dump.

## Pattern / Solution
Use a layered strategy: continuous WAL archiving (PITR) as the primary, logical dumps as a secondary check.

**Logical backup (pg_dump):**
```bash
# Custom format — parallelizable, supports selective restore
pg_dump -Fc -j 4 -d mydb -f mydb_$(date +%Y%m%d).dump

# Restore
pg_restore -Fc -j 4 -d mydb_restore mydb_20260811.dump

# Schema only
pg_dump -Fc --schema-only -d mydb -f schema.dump

# Single table
pg_dump -Fc -t orders -d mydb -f orders.dump
```

**WAL archiving for PITR (postgresql.conf):**
```
wal_level         = replica
archive_mode      = on
archive_command   = 'aws s3 cp %p s3://my-wal-archive/%f'
restore_command   = 'aws s3 cp s3://my-wal-archive/%f %p'
```

**Base backup:**
```bash
pg_basebackup -D /var/lib/postgresql/basebackup -Ft -z -P -Xs -R
# -R writes recovery.conf / standby.signal automatically
```

**pgBackRest (recommended for production PITR):**
```ini
# /etc/pgbackrest/pgbackrest.conf
[global]
repo1-path=/mnt/backup
repo1-retention-full=2
repo1-retention-diff=7
start-fast=y

[mydb]
pg1-path=/var/lib/postgresql/17/main
```

```bash
pgbackrest --stanza=mydb stanza-create
pgbackrest --stanza=mydb backup --type=full
pgbackrest --stanza=mydb backup --type=diff     # daily
pgbackrest --stanza=mydb backup --type=incr     # hourly

# PITR restore to a specific time
pgbackrest --stanza=mydb --delta restore \
  --target="2026-08-11 14:30:00" --target-action=promote
```

**Test your restore (monthly):**
```bash
# Spin up isolated Postgres, restore, run smoke queries
pg_restore -d test_restore mydb_20260811.dump
psql -d test_restore -c "SELECT COUNT(*) FROM orders;"
```

## Gotchas
- A backup that has never been tested restored is not a backup.
- `pg_dump` is not consistent across databases in the same cluster; use `pg_dumpall` for globals (roles, tablespaces).
- WAL archiving must be enabled before taking the base backup; enabling it after the fact leaves a gap.
- `pg_dump` of a large table with TOAST data can be slower than expected — consider partition-level dumps.

## Related
- `postgresql-replication-lag.md`
- `postgresql-vacuum-analyze.md`
- `secrets-vault-rotation.md`
