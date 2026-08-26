# pre-deploy-database-backup

**Issue:** Taking a verified database backup/snapshot before a deployment as a safety net for migration rollback
**Date:** 2026-08-13
**Status:** documented

## Symptom
A deploy runs a schema migration. The migration is destructive —
`ALTER TABLE`, `DROP COLUMN`, a big backfill — and 20 minutes in you
realize it is wrong. The app is down. You want to restore the
database to the state it was in 25 minutes ago, but there is no
recent backup. The last automated snapshot is 23 hours old. You are
now choosing between "extended outage" and "data loss since last
night."

## Root cause
**A migration that changes data is not reversible unless you have a
point-in-time copy taken immediately before it ran.** The deploy
pipeline must capture a verified backup (and confirm it is restorable)
*before* the migration step, as a blocking gate.

**Source:** Platform9 — Containerized Deployments Anti-Patterns
(have a rollback path before destructive change); SEI/CMU — Container
Strategy Leading Practices (recovery posture before deploy).

## The "pre-deploy snapshot gate" pattern

For a managed DB, capture a snapshot as a deploy gate:

```bash
# AWS RDS: create a manual snapshot, block until available
SNAP_ID="api-prod-pre-deploy-$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short HEAD)"
aws rds create-db-snapshot \
  --db-instance-identifier api-prod \
  --db-snapshot-identifier "$SNAP_ID"

# Block the pipeline until the snapshot is "available"
aws rds wait db-snapshot-available \
  --db-snapshot-identifier "$SNAP_ID"

echo "Snapshot $SNAP_ID is available — safe to migrate."
```

The migration step runs only after this command exits 0.

## The "logical backup for surgical restore" pattern

For being able to restore a single table (not the whole DB), take a
logical dump in addition to the snapshot:

```bash
# Postgres: dump the schema(s) being migrated, compressed
pg_dump --format=custom \
        --no-owner --no-privileges \
        --table=users --table=orders \
        "postgres://$USER:$PASS@db.internal:5432/app" \
  > /backups/pre-deploy-$(git rev-parse --short HEAD).dump

# Verify the dump is readable (header check)
pg_restore --list /backups/pre-deploy-*.dump | head
```

A `.dump` lets you restore one table with `pg_restore --table=users`
without rolling back the entire database.

## The "PITR window marker" pattern

For databases with point-in-time recovery, record a marker so you
know exactly where to restore to:

```bash
# Postgres: note the current LSN / timestamp right before the migration
psql "postgres://$USER:$PASS@db.internal:5432/app" -c \
  "SELECT pg_current_wal_lsn(), now();" \
  -t > /backups/restore-marker-$(git rev-parse --short HEAD).txt

# To restore to this point later:
#   pg_receivewal / WAL replay up to the recorded LSN,
#   or managed-DB PITR to the recorded timestamp.
```

```bash
# RDS: restorable time range — confirm PITR is even possible
aws rds describe-db-instances \
  --db-instance-identifier api-prod \
  --query 'DBInstances[0].LatestRestorableTime'
```

If `LatestRestorableTime` is hours old, PITR is not actually
configured — find out now, not during an incident.

## The "verify the backup is restorable" pattern

An untested backup is a hope, not a backup. Restore it to a throwaway
instance before trusting it:

```bash
# Restore the snapshot to a temporary instance and run a smoke query
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier api-prod-verify \
  --db-snapshot-identifier "$SNAP_ID"

aws rds wait db-instance-available --db-instance-identifier api-prod-verify

# Smoke test: can we actually read the data we'd need to restore?
psql "postgres://$USER:$PASS@api-prod-verify.abc.us-east-1.rds.amazonaws.com/app" \
  -c "SELECT count(*) FROM users; SELECT count(*) FROM orders;"

# Tear down the verification instance
aws rds delete-db-instance --db-instance-identifier api-prod-verify --skip-final-snapshot
```

If this fails, the deploy does not proceed.

## The "gate the pipeline" pattern

Wire the backup as a required CI step that fails the deploy on error:

```yaml
# GitHub Actions example
jobs:
  deploy:
    steps:
      - name: Pre-deploy backup (blocking gate)
        id: backup
        run: |
          ./scripts/take-pre-deploy-backup.sh
          if [ $? -ne 0 ]; then
            echo "::error::Pre-deploy backup failed — aborting deploy"
            exit 1
          fi
          echo "marker=$(cat /backups/restore-marker-*.txt)" >> $GITHUB_OUTPUT

      - name: Run migration
        run: ./scripts/migrate.sh
        env:
          RESTORE_MARKER: ${{ steps.backup.outputs.marker }}

      - name: Smoke test
        run: ./scripts/smoke.sh
```

A failed backup step stops the deploy before any migration runs.

## The "document the restore command" pattern

For the on-call engineer at 3 a.m., the backup is useless if they
cannot remember how to restore it. Write the exact command into the
runbook alongside the marker:

```bash
# Restore command (fill in MARKER from the pre-deploy artifact):
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier api-prod \
  --target-db-instance-identifier api-prod-restored \
  --restore-time "2026-08-13T02:14:00Z"   # <- from restore-marker file

# Or for the logical dump:
pg_restore --clean --if-exists \
  --table=users \
  -d "postgres://$USER:$PASS@db.internal/app" \
  /backups/pre-deploy-abc1234.dump
```

Store the marker file with the build artifact so it is retrievable
during an incident.

## Verification
- **Test:** Trigger the backup step, then immediately restore it to
  a temp instance and run a query. Must succeed every deploy.
- **Test:** Force the backup step to fail (e.g., wrong credentials)
  — the pipeline must abort the deploy.
- **Audit:** Monthly — restore a random pre-deploy backup to a temp
  instance to prove the restore path actually works end-to-end.

## Gotchas
- **The "snapshot started, migrate anyway" anti-pattern.** A snapshot
  in `creating` state is not restorable yet. Block until `available`.
- **The "untested backup" anti-pattern.** A snapshot you have never
  restored from may be corrupt or permission-blocked. Test restores
  monthly.
- **The "no restore marker" anti-pattern.** Without a recorded
  timestamp/LSN, you will guess the restore point under stress and
  lose or duplicate data.
- **The "backup only, no logical dump" anti-pattern.** A full-DB
  snapshot cannot restore a single table. For surgical rollbacks,
  also take a logical dump of the affected tables.

## Related
- `database-migration-deploy-strategy.md`
- `database-blue-green-migration.md`
- `blue-green-database-cutover.md`
- `rollback-runbook.md`
- `database-connection-drain.md`
