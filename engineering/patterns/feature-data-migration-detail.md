# feature-data-migration-detail

**Issue:** Data migration — when schema changes, backfill, verify
**Date:** 2026-08-09
**Status:** documented

## Symptom
You change the schema. You add a `display_name` column.
You write a migration to backfill from `name`. The
migration runs. The data is wrong. Some users have
`display_name = null`. The app crashes for them.

## Root cause
**Migrations are not "ALTER TABLE then forget."** You
need to backfill, verify, and monitor.

**Source:** Stripe data migrations:
https://stripe.com/blog/data-migration-tooling

## The "expand-migrate-contract" pattern

For zero-downtime migrations:
1. **Expand:** Add the new column (NULL or default)
2. **Migrate:** Backfill the new column from the old
3. **Contract:** Drop the old column (after deploy is
   done)

```sql
-- Step 1: Expand
ALTER TABLE users ADD COLUMN display_name TEXT;

-- Step 2: Migrate (in batches)
UPDATE users SET display_name = name WHERE display_name IS NULL AND id BETWEEN '0' AND '1000000';
UPDATE users SET display_name = name WHERE display_name IS NULL AND id BETWEEN '1000001' AND '2000000';

-- Step 3: Contract (after code is deployed)
ALTER TABLE users DROP COLUMN name;
```

## The "dual writes" pattern

For migrations that change the data shape:
```ts
// 1. Write to both old and new
async function updateUser(id: string, data: UserUpdate, env: Env): Promise<User> {
  // Old
  await env.DB!.prepare(
    `UPDATE users SET name = ? WHERE id = ?`
  ).bind(data.displayName, id).run();

  // New
  await env.DB!.prepare(
    `UPDATE users SET display_name = ? WHERE id = ?`
  ).bind(data.displayName, id).run();

  return { ... };
}

// 2. Read from old (until new is verified)
async function getUser(id: string, env: Env): Promise<User | null> {
  const row = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  return { ...row, displayName: row.name };  // Read from old
}

// 3. After verification, switch reads
async function getUser(id: string, env: Env): Promise<User | null> {
  const row = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
  return row;  // Read from new
}
```

## The "batch size" pattern

For large backfills, batch the work:
```ts
async function backfillDisplayName(env: Env, batchSize = 1000): Promise<void> {
  let lastId = '';

  while (true) {
    const batch = await env.DB!.prepare(
      `SELECT id, name FROM users WHERE display_name IS NULL AND id > ? ORDER BY id LIMIT ?`
    ).bind(lastId, batchSize).all<User>();

    if (batch.results.length === 0) break;

    for (const user of batch.results) {
      await env.DB!.prepare(
        `UPDATE users SET display_name = ? WHERE id = ?`
      ).bind(user.name, user.id).run();
    }

    lastId = batch.results[batch.results.length - 1].id;

    // Log progress
    console.log({ msg: 'migration.progress', migrated: batch.results.length, lastId });

    // Throttle
    await new Promise(r => setTimeout(r, 100));
  }
}
```

The batch size is small enough to not lock the DB.

## The "migration progress" pattern

Track the migration progress:
```ts
// Add a migration log
await env.DB!.prepare(`
  CREATE TABLE IF NOT EXISTS migration_log (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    rows_migrated INTEGER DEFAULT 0
  )
`).run();

// Start the migration
await env.DB!.prepare(
  `INSERT INTO migration_log (id, name, status, started_at) VALUES (?, ?, ?, ?)`
).bind(crypto.randomUUID(), 'add-display-name', 'in_progress', new Date().toISOString()).run();

// Update the progress
await env.DB!.prepare(
  `UPDATE migration_log SET rows_migrated = ? WHERE id = ?`
).bind(rowsMigrated, migrationId).run();

// Complete
await env.DB!.prepare(
  `UPDATE migration_log SET status = ?, completed_at = ? WHERE id = ?`
).bind('completed', new Date().toISOString(), migrationId).run();
```

The log shows the migration's progress + status.

## The "migration verification" pattern

After the migration, verify the data:
```ts
async function verifyMigration(env: Env): Promise<{ ok: boolean; issues: string[] }> {
  const issues: string[] = [];

  // 1. Check for null display_names
  const nulls = await env.DB!.prepare(
    `SELECT COUNT(*) AS count FROM users WHERE display_name IS NULL`
  ).first<{ count: number }>();
  if (nulls && nulls.count > 0) {
    issues.push(`${nulls.count} users have null display_name`);
  }

  // 2. Check the data matches
  const mismatches = await env.DB!.prepare(
    `SELECT COUNT(*) AS count FROM users WHERE name != display_name AND name IS NOT NULL`
  ).first<{ count: number }>();
  if (mismatches && mismatches.count > 0) {
    issues.push(`${mismatches.count} users have display_name != name`);
  }

  return { ok: issues.length === 0, issues };
}
```

The verification catches issues before the contract step.

## The "rollback" pattern

If the migration is bad:
1. **Stop the migration** (set status to 'paused')
2. **Identify the issue**
3. **Roll back the data** (if possible)
4. **Fix the migration**
5. **Re-run the migration**

```ts
// Stop the migration
await env.DB!.prepare(
  `UPDATE migration_log SET status = 'paused' WHERE id = ?`
).bind(migrationId).run();

// In the migration worker
if (migration.status === 'paused') return;
```

## The "monitoring" pattern

Monitor the migration in real-time:
```ts
// Emit metrics
metrics.gauge('migration.progress', rowsMigrated / totalRows);
metrics.gauge('migration.duration_seconds', (Date.now() - startedAt) / 1000);

// Alert if stuck
if (Date.now() - lastUpdate > 60_000) {
  pageOncall('Migration stuck', { migrationId, lastUpdate });
}
```

## The "data integrity" pattern

After the migration, check invariants:
- **Unique constraints:** Are there any duplicates?
- **Foreign keys:** Are all FKs valid?
- **NOT NULL:** Are there any nulls in NOT NULL columns?
- **Business rules:** Are the business rules satisfied?

```ts
test('migration: all users have a display_name', async () => {
  await applyMigrations();
  const result = await db.prepare(`SELECT COUNT(*) AS count FROM users WHERE display_name IS NULL`).first();
  expect(result.count).toBe(0);
});
```

## The "migration" anti-patterns

### 1. Migration without backfill
```sql
-- ❌ Adds a NOT NULL column with no default
ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL;
-- All existing rows are invalid
```

Always provide a default or backfill.

### 2. Migration in a single transaction
```ts
// ❌ One big transaction
await db.transaction(async (txn) => {
  for (const user of allUsers) {
    await txn.prepare(`UPDATE ...`).bind(...).run();
  }
});
// Locks the table; times out
```

Batch the work; don't do it in one transaction.

### 3. Migration without tests
- **Symptom:** The migration ships; the data is wrong
- **Fix:** Test the migration with production-scale data

### 4. Migration without rollback
- **Symptom:** The migration is bad; you can't undo it
- **Fix:** Plan the rollback before the migration

## The "D1 migration" specifics

D1 (SQLite) has some specifics:
- **ALTER TABLE ADD COLUMN:** Fast (just updates the
  schema)
- **ALTER TABLE DROP COLUMN:** Supported (since 2024)
- **ALTER TABLE RENAME COLUMN:** Supported
- **CREATE INDEX:** Can be slow on large tables
- **CREATE TABLE AS SELECT:** Useful for full table
  rewrites

For D1, prefer "expand-migrate-contract" over destructive
migrations.

## Verification
- **Test:** Migration runs + verifies
- **Test:** Migration is reversible
- **Live:** Migration is monitored
- **Audit:** Quarterly review of migrations

## Gotchas
- **The "fast in dev, slow in prod" gotcha.** A migration
  that runs in 1s on 10 rows may take hours on 10M rows.
- **The "no backfill" gotcha.** Adding a column without
  backfilling leaves the data inconsistent.
- **The "no verification" gotcha.** The migration ran
  successfully, but the data is wrong. Verify.
- **The "no rollback" gotcha.** Plan the rollback before
  the migration.
- **The "concurrent writes" gotcha.** New rows are added
  during the migration. The migration must handle them.

## Related
- `database-migration-strategy.md`
- `cloudflare/d1-migration-best-practices.md`
- `data-migration-strategies.md`
- `zero-downtime-db-migration.md`
- `soft-delete-pattern-detail.md`
- `audit-log-as-product.md`
- Stripe: https://stripe.com/blog/data-migration-tooling
