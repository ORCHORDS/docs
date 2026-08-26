# database-backup-strategies

**Issue:** Backups exist but are untested, incomplete, or too infrequent for RTO/RPO requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Incident occurs, backup restore takes 8 hours, or backup file is corrupt. No tested restore procedure.

## Pattern / Solution
Backup types: logical (pg_dump -- portable, slow to restore at scale), physical/base backup (pg_basebackup -- fast restore), WAL archiving (continuous, enables PITR). Strategy: daily base backup + continuous WAL archiving = PITR capability. Test restores monthly. Automate with pgBackRest or Barman.

## Gotchas
- pg_dump is consistent but does not include WAL -- cannot do PITR from logical backups alone
- Backup without restore test is not a backup -- automate weekly restore to staging
- Encrypted backups require secure key management -- losing the key means losing data

## Related
- point-in-time-recovery
- database-encryption-at-rest
- sqlite-wal-mode
