# d1-migration-best-practices

**Issue:** D1 schema migrations — versioning, safety, rollback
**Date:** 2026-08-09
**Status:** documented

## Symptom
You add a `display_name` column to the `users` table. You
run `ALTER TABLE users ADD COLUMN display_name TEXT;` in
production. The query takes 10 seconds. The app is down
for 10 seconds. Users see errors.

## Root cause
**Schema migrations are dangerous.** A migration that
works on a small dev DB may lock a large production DB.

**Source:** CF D1 migrations:
https://developers.cloudflare.com/d1/platform/migrations/

## The "migration" pattern in D1

```bash
# Create a migration
wrangler d1 migrations create my-db add_display_name
# Creates migrations/0001_add_display_name.sql
```

```sql
-- migrations/0001_add_display_name.sql
ALTER TABLE users ADD COLUMN display_name TEXT;
```

```bash
# Apply locally
wrangler d1 migrations apply my-db --local

# Apply to production
wrangler d1 migrations apply my-db --remote
```

The migration is versioned, ordered, and tracked in a
metadata table.

## The "migration metadata" table

D1 stores migration state in a `d1_migrations` table:
```sql
CREATE TABLE d1_migrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

When you apply a migration, the row is added. When you
list migrations, the rows are shown.

## The "backwards-compatible" rule

For zero-downtime, every migration must be backwards-
compatible:
- **Additive:** New columns, new tables, new indexes
- **Non-destructive:** No DROP, no type changes
- **Optional:** New code can use the new schema; old code
  can still work

```sql
-- ✅ Additive (safe)
ALTER TABLE users ADD COLUMN display_name TEXT;

-- ❌ Destructive (NOT safe)
ALTER TABLE users DROP COLUMN email;
```

For destructive changes, do them in two steps:
1. **Expand:** Add the new column
2. **Migrate:** Backfill the new column from the old
3. **Contract:** Drop the old column (after all code uses
   the new)

## The "deploy order" rule

For a migration + code change, the order is:
1. **Deploy the migration** (additive)
2. **Deploy the code** (use the new column)
3. **Backfill** the new column (if needed)
4. **Deploy the code** (use the backfilled data)
5. **Deploy the migration** (drop the old column)

Reverse the order for rollback.

## The "rollback" plan

D1 doesn't support automatic rollback. The plan:
1. **Code rollback:** Deploy the old code (which doesn't
   use the new column)
2. **Migration rollback:** Add a new migration that reverses
   the previous (e.g. `ALTER TABLE users DROP COLUMN ...`)

For destructive changes, the rollback is complex (the data
is gone). Test the rollback in staging.

## The "migration in CI" pattern

In CI, run migrations against a test DB:
```yaml
- name: Test migrations
  run: |
    wrangler d1 migrations apply my-db-test --local
    npm test
    # Check no test fails after the migration
```

If a test fails, the migration broke something.

## The "large table" pattern

For a 1M+ row table, ALTER TABLE may lock. The pattern:
1. **Create a new table** with the new schema
2. **Backfill** the new table from the old
3. **Switch** the code to read from the new table
4. **Drop** the old table (after verification)

This is a "blue-green" migration. More complex, but
zero-downtime.

## The "add NOT NULL column" gotcha

```sql
-- ❌ This locks the table on Postgres
ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT '';
-- On Postgres, the DEFAULT rewrite is expensive

-- ✅ D1 / SQLite is OK with this (no rewrite)
-- But still test on large tables
```

For D1, the `ALTER TABLE ADD COLUMN` is fast (just updates
the schema). But for large tables, always test.

## The "PRAGMA" pattern

For specific tuning:
```sql
PRAGMA journal_mode = WAL;  -- Write-Ahead Logging
PRAGMA synchronous = NORMAL;  -- Default is FULL
PRAGMA cache_size = -2000;  -- 2MB cache
PRAGMA temp_store = MEMORY;
```

D1 doesn't support all PRAGMAs (it's server-side). But
local dev does.

## The "schema documentation" pattern

Document the schema in a separate file:
```markdown
# Schema

## users
- `id` TEXT PK — UUID
- `email` TEXT NOT NULL — User's email
- `display_name` TEXT — User's display name
- `created_at` TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
- `deleted_at` TEXT — Soft delete timestamp

Indexes:
- `idx_users_email` ON (email)
- `idx_users_tenant` ON (tenant_id)
```

The docs are kept up to date; the schema is the source of
truth.

## The "test migration" pattern

For every migration, write a test:
```ts
test('migration 0001 adds display_name', async () => {
  await applyMigrations(['0001_add_display_name']);
  const columns = await db.prepare(`PRAGMA table_info(users)`).all();
  expect(columns.results.find(c => c.name === 'display_name')).toBeDefined();
});
```

The test verifies the migration does what it claims.

## Verification
- **Test:** Migrations apply + reverse correctly
- **Live:** Migrations are reviewed before apply
- **Audit:** Quarterly review of migration history

## Gotchas
- **The "D1 doesn't support all SQL" gotcha.** D1 is SQLite-
  based; some Postgres features are not supported (e.g.
  partial indexes in some forms, some ALTER TABLE
  operations).
- **The "D1 max 10MB per request" gotcha.** A migration
  that returns a lot of data is limited. For backfills, use
  multiple requests.
- **The "D1 is read-replicated" gotcha.** Writes go to the
  primary; reads may be from a replica. After a write, a
  subsequent read may not see the change (eventual
  consistency).
- **The "ALTER TABLE in D1" gotcha.** Some ALTER TABLE
  operations are slow on large tables. Always test in
  staging with production-scale data.

## Related
- `database-migration-strategy.md`
- `data-migration-strategies.md`
- `zero-downtime-db-migration.md`
- `cloudflare/d1-batch-bundler-bug.md`
- CF D1 migrations: https://developers.cloudflare.com/d1/platform/migrations/
- SQLite ALTER TABLE: https://www.sqlite.org/lang_altertable.html
