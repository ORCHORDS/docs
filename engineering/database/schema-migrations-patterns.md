# schema-migrations-patterns

**Issue:** Managing schema changes safely with versioned migration files
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Ad-hoc schema changes applied directly to production lead to drift between environments and no rollback path.

## Pattern / Solution
```sql
-- Migration file: V20260811_001__add_user_preferences.sql
BEGIN;

ALTER TABLE users ADD COLUMN preferences JSONB NOT NULL DEFAULT ''{}''::jsonb;
CREATE INDEX idx_users_preferences ON users USING GIN (preferences);

COMMIT;

-- Always: one migration = one logical change
-- Always: test migration on a copy of production data first
-- Always: include rollback script or make migration reversible
```

## Gotchas
- Never modify a committed migration file — create a new one to fix mistakes
- Large table ALTERs can lock the table; prefer concurrent index creation and batch backfills
- Keep migrations small and focused; avoid bundling unrelated changes

## Related
- `zero-downtime-migrations.md`
- `backward-compatible-migrations.md`
- `flyway-liquibase-patterns.md`
