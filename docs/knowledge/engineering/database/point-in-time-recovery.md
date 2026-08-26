# point-in-time-recovery

**Issue:** Restoring to a specific moment before data corruption or accidental deletion
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developer ran DELETE FROM orders without WHERE clause at 14:32. Need to restore orders as of 14:31 without losing all other data changed since last full backup.

## Pattern / Solution
Postgres PITR: configure archive_mode = on and archive_command to ship WAL to object storage. To recover: restore base backup, then replay WAL to target time using recovery_target_time. pgBackRest simplifies this significantly.

## Gotchas
- WAL archiving must be configured BEFORE the incident -- cannot retroactively enable
- Recovery target time must be before the bad operation but after last checkpoint
- Verify WAL archive completeness regularly; gaps break PITR chain

## Related
- database-backup-strategies
- vacuum-and-bloat-postgres
- postgres-configuration-tuning
