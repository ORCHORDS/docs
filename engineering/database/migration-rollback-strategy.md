# migration-rollback-strategy

**Issue:** Planning and implementing rollback for failed migrations
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A migration deploys and causes issues — you need to revert the schema without losing data.

## Pattern / Solution
```sql
-- Flyway undo migration (paid feature)
-- V2__add_column.sql  →  U2__add_column.sql
-- U2__add_column.sql
ALTER TABLE orders DROP COLUMN IF EXISTS notes;

-- Manual rollback script alongside each migration
-- migrations/
--   20260811_add_notes.up.sql
--   20260811_add_notes.down.sql

-- For non-destructive changes, rollback is easy
-- For destructive changes (DROP TABLE), backup first:
-- pg_dump --table=orders production > orders_backup.sql
```

## Gotchas
- Data-destructive migrations (DROP COLUMN, DELETE) cannot be undone without a backup
- Test rollback scripts in staging before every production migration
- Blue/green deployment is more reliable than rollback scripts for high-risk changes

## Related
- `schema-migrations-patterns.md`
- `database-backup-strategies.md`
