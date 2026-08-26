# database-migration-strategy

**Issue:** Schema migrations without downtime
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need to add a column to a 100M-row table. You run
`ALTER TABLE ADD COLUMN`. The migration takes 30 minutes. The
table is locked for the duration. Users see timeouts.

## Root cause
**DDL operations (CREATE, ALTER, DROP) lock the table.** On
D1, the lock is per-statement; on Postgres it's often
table-level. Long-running locks block reads + writes.

**Source:** D1 limits:
https://developers.cloudflare.com/d1/platform/limits/

> "D1 supports SQLite's transactional DDL. ... However, ALTER
> TABLE on a large table can be slow."

## Fix
A 3-phase migration strategy:

### Phase 1: Additive (no breaking changes)
- **Add** new columns (nullable, with defaults)
- **Add** new tables
- **Add** new indexes (concurrently if possible)

These are safe. The new code can write to them; the old code
ignores them.

```sql
-- Add a new nullable column
ALTER TABLE users ADD COLUMN display_name_new TEXT;
-- Add an index (slow but doesn't lock writes)
CREATE INDEX idx_users_display_name_new ON users(display_name_new);
```

### Phase 2: Dual-write (during the transition)
The new code writes to BOTH the old and new columns. The old
code continues to work.

```ts
// During the transition
async function updateUser(id: string, changes: Partial<User>): Promise<void> {
  await env.DB!.batch([
    env.DB!.prepare(`UPDATE users SET display_name = ? WHERE id = ?`).bind(changes.displayName, id),
    // NEW: also write to the new column
    env.DB!.prepare(`UPDATE users SET display_name_new = ? WHERE id = ?`).bind(changes.displayName, id),
  ]);
}
```

### Phase 3: Backfill + cutover
- Backfill the new column from the old
- Verify the new column is fully populated
- Switch reads to the new column
- Remove the old column (in a future migration)

```ts
// 1. Backfill (slow, can be done in chunks)
async function backfillDisplayName(env: Env): Promise<void> {
  let lastId = '';
  while (true) {
    const rows = await env.DB!.prepare(
      `SELECT id FROM users WHERE display_name_new IS NULL AND id > ?
       ORDER BY id LIMIT 1000`
    ).bind(lastId).all<{ id: string }>();
    if (rows.results.length === 0) break;
    for (const row of rows.results) {
      await env.DB!.prepare(
        `UPDATE users SET display_name_new = display_name WHERE id = ?`
      ).bind(row.id).run();
    }
    lastId = rows.results[rows.results.length - 1].id;
  }
}

// 2. Cutover (after backfill is done)
async function cutoverRead(env: Env): Promise<void> {
  // Update the code to read from display_name_new
  // Deploy
  // After 1 week, remove display_name (the old column)
}
```

## Migrations for D1 specifically

D1 supports `db.batch()` for multiple statements in one
transaction. BUT the bundler bug (`d1-batch-bundler-bug.md`)
strips the `sql` field in some cases. Use `db.exec()` for DDL
and `db.prepare().run()` for DML.

For local dev, use `wrangler d1 execute`:
```bash
# Run a migration
wrangler d1 execute example project-prod --file db/0082_engine_ingestion.sql

# For preview
wrangler d1 execute example project-preview --file db/0082_engine_ingestion.sql
```

## Migration tracking

Always track which migrations have been applied:
```sql
CREATE TABLE IF NOT EXISTS migrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  applied_at INTEGER NOT NULL
);
```

```ts
async function applyMigrations(env: Env): Promise<void> {
  const applied = await env.DB!.prepare(
    `SELECT name FROM migrations`
  ).all<{ name: string }>();
  const appliedSet = new Set(applied.results.map(r => r.name));

  for (const file of migrationFiles) {
    if (appliedSet.has(file.name)) continue;
    const sql = await Deno.readTextFile(file.path);
    await env.DB!.exec(sql);
    await env.DB!.prepare(
      `INSERT INTO migrations (name, applied_at) VALUES (?, ?)`
    ).bind(file.name, Date.now()).run();
  }
}
```

## Naming convention

`db/NNNN_short_description.sql`:
- `0001_users.sql`
- `0002_posts.sql`
- `0082_engine_ingestion.sql`

The `NNNN` is a sequential number. **Never reuse a number.**
**Never edit a merged migration file** (add a new one instead).

## Verification
- **Test:** `test/migrations.test.ts` — apply all migrations
  fresh; apply incrementally; rollback (if supported)
- **Live:** Migrations apply in < 5 minutes (even on prod)
- **Audit:** Review of schema changes for breaking changes

## Gotchas
- **D1 ALTER TABLE on a large table is slow.** The query plan
  shows the time. For tables > 1M rows, consider the
  additive-then-cutover pattern.
- **CF D1 is SQLite under the hood.** SQLite has limited
  ALTER TABLE support. Renaming a column requires recreating
  the table.
- **Migrations are forward-only.** Don't add a "down" migration
  unless you have a strong reason (e.g. you discovered a bug
  in the up). Forward-only is simpler.
- **Production migrations are a deploy step.** They run BEFORE
  the new code. If the migration fails, the new code can't
  be deployed.
- **For multi-region, schema migration is per-region.** A new
  D1 database is per-region. Migrations must run in all
  regions.

## Related
- `d1-batch-bundler-bug.md`
- `soft-delete-pattern.md` (additive migration example)
- `zero-downtime-deploys.md` (the deploy coordination)
- CF D1 migrations: https://developers.cloudflare.com/d1/platform/migrations/
