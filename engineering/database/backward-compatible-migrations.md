# backward-compatible-migrations

**Issue:** Writing migrations that allow old and new app versions to coexist
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Blue/green or rolling deploys require the database to work with both old and new application versions simultaneously.

## Pattern / Solution
```
Rename column safely:
1. Add new column (new_name)
2. Write to both old and new columns in the app
3. Backfill new column from old
4. Read from new column in the app
5. Remove old column in a later migration

Delete column safely:
1. Stop reading/writing the column in the app
2. Deploy app
3. Drop column in next migration cycle

Change column type safely:
1. Add new column with new type
2. Dual-write
3. Backfill
4. Switch reads
5. Drop old column
```

## Gotchas
- Never rename a column in a single migration if old app code references the old name
- Adding NOT NULL with no default is not backward-compatible if old app doesn''t write the column
- Check constraint changes need the same phased approach

## Related
- `zero-downtime-migrations.md`
- `schema-migrations-patterns.md`
