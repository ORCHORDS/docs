# zero-downtime-db-migration

**Issue:** How to deploy a schema change without downtime
**Date:** 2026-08-09
**Status:** documented

## Symptom
You add a `NOT NULL` column to a 10M-row table. The migration
takes 20 minutes. The table is locked. Users see 5xx errors.

## Root cause
**DDL operations lock the table.** On D1 (SQLite), the lock
is per-statement but on a large table, the write itself is
slow. For other DBs (Postgres, MySQL), the lock can be
table-level, blocking all reads + writes.

**Source:** D1 limits:
https://developers.cloudflare.com/d1/platform/limits/

> "ALTER TABLE on a large table is slow. ... D1's underlying
> SQLite ... performs the operation as a single transaction."

## The 3-phase migration

### Phase 1: Add nullable (no breaking change)
```sql
-- Add the new column, nullable, no default
ALTER TABLE users ADD COLUMN display_name_new TEXT;
```

✅ Safe: existing rows have NULL; new rows can set a value.
The app ignores the column.

### Phase 2: Dual-write (during the transition)
The new app code writes to BOTH old and new columns:
```ts
async function updateUser(id: string, changes: Partial<User>): Promise<void> {
  await env.DB!.prepare(
    `UPDATE users SET
       display_name = COALESCE(?, display_name),
       display_name_new = COALESCE(?, display_name_new)
     WHERE id = ?`
  ).bind(changes.displayName, changes.displayName, id).run();
}
```

### Phase 3: Backfill (slow, can be chunked)
```ts
async function backfillDisplayName(env: Env): Promise<void> {
  let lastId = '';
  while (true) {
    const rows = await env.DB!.prepare(
      `SELECT id FROM users
       WHERE display_name_new IS NULL AND id > ?
       ORDER BY id LIMIT 1000`
    ).bind(lastId).all<{ id: string }>();
    if (rows.results.length === 0) break;
    for (const row of rows.results) {
      await env.DB!.prepare(
        `UPDATE users SET display_name_new = display_name WHERE id = ?`
      ).bind(row.id).run();
    }
    lastId = rows.results[rows.results.length - 1]!.id;
  }
}
```

### Phase 4: Cutover (after backfill is done)
The new app code reads from `display_name_new`:
```ts
const user = await env.DB!.prepare(
  `SELECT id, display_name_new AS display_name, ... FROM users WHERE id = ?`
).bind(id).first();
```

### Phase 5: Remove the old column (later migration)
```sql
-- SQLite doesn't support DROP COLUMN; you have to recreate the table
CREATE TABLE users_new (...);
INSERT INTO users_new SELECT ... FROM users;
DROP TABLE users;
ALTER TABLE users_new RENAME TO users;
```

Or just leave the old column (it's small).

## Zero-downtime index creation

Adding an index also locks the table. For Postgres:
```sql
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);
```

`CONCURRENTLY` builds the index without taking an exclusive
lock. Slower but no downtime.

For D1, there's no CONCURRENTLY. You must accept the lock or
use a separate migration strategy.

## The "expand-contract" pattern

For complex changes, use the "expand-contract" pattern:

### Expand
- Add new columns, new tables, new code paths
- Old code still works
- New code writes to both

### Migrate
- Backfill new columns
- Switch reads to new columns
- Old code can stay (just writes to old columns)

### Contract
- Remove old columns, old code paths
- One final migration

The whole process takes days/weeks. The key is that **no
single deploy causes downtime**.

## Example: rename a column

| Step | Action | Code |
|---|---|---|
| 1 | Add new column | `ALTER TABLE posts ADD COLUMN body_v2 TEXT` |
| 2 | Dual-write | App writes to both `body` and `body_v2` |
| 3 | Backfill | Cron copies `body` → `body_v2` for old rows |
| 4 | Read from new | App reads from `body_v2` only |
| 5 | Stop writing to old | App writes to `body_v2` only |
| 6 | Drop old column | (in SQLite: recreate the table) |

## Verification
- **Test:** `test/migration.test.ts > migration is non-blocking`
  — passes
- **Live:** The deploy + migration is monitored
- **Audit:** Quarterly review of migration procedures

## Gotchas
- **A `NOT NULL` column with no default** fails on existing
  rows. Add it nullable first, then backfill, then add the
  constraint.
- **A `DEFAULT` on a NOT NULL column** triggers a table rewrite
  on some DBs (e.g. Postgres). Slow on a large table.
- **Foreign key constraints** also lock. Add them carefully.
- **The migration order matters.** If you have multiple
  migrations, apply them in order. Some DBs have `atomic
  migrations` (each migration is a transaction); some don't.
- **D1 doesn't have native `CONCURRENTLY`.** For zero-
  downtime index adds, you may need to:
  - Create the new table with the index
  - Copy data from the old table
  - Swap the table names

## Related
- `database-migration-strategy.md` (the broader migration story)
- `zero-downtime-deploys.md` (the deploy coordination)
- `d1-batch-bundler-bug.md` (D1-specific gotcha)
- Stripe: https://stripe.com/blog/online-migrations
- GitHub: https://github.blog/engineering/enhancing-github-archives/
