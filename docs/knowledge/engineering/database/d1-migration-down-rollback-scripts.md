# D1 Down / Rollback Migration Scripts

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A schema migration shipped to production breaks the app. You need to revert the
schema change quickly, but `wrangler d1 migrations apply --remote` only runs
*up* migrations — there is no built-in `down` command. You need a reliable,
auditable rollback path for D1.

## Context

Wrangler's migration system tracks which `.sql` files in `migrations/` have
been applied via the `d1_migrations` table. It has no concept of rollback or
down scripts. Teams coming from Flyway, Liquibase, or Prisma Migrate expect
versioned down migrations; with D1 you must implement this discipline yourself.

Because SQLite (and D1) do not support `ALTER TABLE … DROP COLUMN` in all
older SQLite builds and do not support transactional DDL that auto-rolls back on
failure, down migrations require a careful table-rebuild pattern for destructive
changes.

---

## Implementing a Down Migration System

### Directory Layout

```
migrations/
  0001_create_users.up.sql
  0001_create_users.down.sql
  0002_add_users_email_index.up.sql
  0002_add_users_email_index.down.sql
  0003_add_orders_table.up.sql
  0003_add_orders_table.down.sql
```

Wrangler only applies `*.up.sql` files (or any `.sql` file matching its
configured pattern). Keep `.down.sql` files in the same directory — they are
ignored by Wrangler but managed by your custom rollback script.

### Migration Tracking Table

Wrangler creates `d1_migrations` automatically. Add your own column to track
the *previous* version so rollback knows what to target:

```sql
-- run once, idempotent
ALTER TABLE d1_migrations ADD COLUMN rolled_back_at TEXT;
```

Or maintain a separate audit table:

```sql
CREATE TABLE IF NOT EXISTS migration_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  version     TEXT    NOT NULL,
  direction   TEXT    NOT NULL CHECK (direction IN ('up','down')),
  applied_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  applied_by  TEXT
);
```

---

## Rollback Worker Script

```typescript
// scripts/rollback-migration.ts
// Run with: npx tsx scripts/rollback-migration.ts <version> <env>

import { execSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";

const MIGRATIONS_DIR = "./migrations";

interface AppliedMigration {
  Name: string;
  Status: string;
}

async function getAppliedMigrations(database: string, env: string): Promise<AppliedMigration[]> {
  const flag = env === "production" ? "--remote" : "--local";
  const raw = execSync(
    `npx wrangler d1 migrations list ${database} ${flag} --json`,
    { encoding: "utf8" }
  );
  return JSON.parse(raw) as AppliedMigration[];
}

async function rollback(database: string, version: string, env: string): Promise<void> {
  const flag = env === "production" ? "--remote" : "--local";

  const applied = await getAppliedMigrations(database, env);
  const isApplied = applied.some(m => m.Name.startsWith(version) && m.Status === "Applied");

  if (!isApplied) {
    throw new Error(`Migration ${version} is not applied — nothing to roll back.`);
  }

  const downFile = path.join(MIGRATIONS_DIR, `${version}.down.sql`);
  if (!existsSync(downFile)) {
    throw new Error(`No down script found at ${downFile}`);
  }

  const sql = readFileSync(downFile, "utf8");
  console.log(`Rolling back migration ${version} on ${env}…`);

  // Execute via wrangler execute (pipes stdin SQL)
  execSync(
    `npx wrangler d1 execute ${database} ${flag} --command "${sql.replace(/"/g, '\\"')}"`,
    { stdio: "inherit" }
  );

  // Remove from wrangler tracking table so it can be re-applied later
  execSync(
    `npx wrangler d1 execute ${database} ${flag} ` +
    `--command "DELETE FROM d1_migrations WHERE Name LIKE '${version}%'"`,
    { stdio: "inherit" }
  );

  console.log(`Rolled back ${version} successfully.`);
}

// CLI entry point
const [,, version, env = "local"] = process.argv;
if (!version) {
  console.error("Usage: npx tsx scripts/rollback-migration.ts <version_prefix> [local|production]");
  process.exit(1);
}
rollback("my-database", version, env).catch(err => {
  console.error(err);
  process.exit(1);
});
```

---

## Writing Safe Down Scripts

### For index drops (trivially reversible):

```sql
-- 0002_add_users_email_index.down.sql
DROP INDEX IF EXISTS idx_users_email;
```

### For column additions (SQLite 3.35+, D1 supports DROP COLUMN):

```sql
-- 0004_add_users_avatar_url.down.sql
ALTER TABLE users DROP COLUMN avatar_url;
```

### For table creation (destructive — guard with data check):

```sql
-- 0003_add_orders_table.down.sql
-- DANGER: drops all order data
DROP TABLE IF EXISTS orders;
```

### For column type changes (requires table rebuild):

```sql
-- 0005_widen_users_bio.down.sql
-- Revert TEXT bio back to VARCHAR(255) simulation via CHECK constraint
BEGIN;
  CREATE TABLE users_old AS SELECT * FROM users;
  DROP TABLE users;
  CREATE TABLE users (
    id   INTEGER PRIMARY KEY,
    name TEXT    NOT NULL,
    bio  TEXT    CHECK(length(bio) <= 255)
  );
  INSERT INTO users SELECT id, name, bio FROM users_old;
  DROP TABLE users_old;
COMMIT;
```

---

## CI Guard: Require Down Scripts for Every Up Script

```typescript
// scripts/check-down-scripts.ts — run in CI before merging
import { readdirSync, existsSync } from "node:fs";
import path from "node:path";

const dir = "./migrations";
const upFiles = readdirSync(dir).filter(f => f.endsWith(".up.sql"));

let missing = 0;
for (const up of upFiles) {
  const down = up.replace(".up.sql", ".down.sql");
  if (!existsSync(path.join(dir, down))) {
    console.error(`Missing down script for: ${up}`);
    missing++;
  }
}

if (missing > 0) process.exit(1);
console.log("All up migrations have corresponding down scripts.");
```

Add to `package.json`:
```json
{
  "scripts": {
    "migrations:check": "npx tsx scripts/check-down-scripts.ts"
  }
}
```

---

## Anti-patterns

- **Deleting or editing the `.up.sql` file to "undo"**: Wrangler's tracking
  table still shows the migration as applied; the schema state diverges from
  what Wrangler believes.
- **Using `wrangler d1 execute` with a raw DROP without testing locally first**:
  always test down scripts against `--local` before `--remote`.
- **Skipping the `d1_migrations` table cleanup**: if you run the down SQL but
  don't remove the row, Wrangler won't re-apply the up script when you're ready.
- **Non-idempotent down scripts**: always use `DROP TABLE IF EXISTS`,
  `DROP INDEX IF EXISTS`, `ALTER TABLE ... DROP COLUMN IF EXISTS` so accidental
  double-runs are safe.

---

## Gotchas

- SQLite DDL statements (CREATE TABLE, DROP TABLE, CREATE INDEX) are **not**
  transactional in the ACID sense within D1's HTTP API — a partial failure can
  leave schema in an inconsistent state. Use the table-rebuild pattern inside
  `BEGIN … COMMIT` for multi-step downs.
- D1's `--remote` flag runs against the production edge replica; there is no
  dry-run mode. Always verify against `--local` (Miniflare) first.
- Wrangler tracks applied migrations by filename prefix match; if your version
  prefix is `0003`, a migration named `0003_foo.up.sql` and `00030_bar.up.sql`
  would both match. Use zero-padded 4-digit prefixes to avoid collisions.
- `DROP COLUMN` on a column that is part of an index or a foreign key will
  fail. Drop the index/FK constraint first in the down script.

---

## Verification

```bash
# 1. Apply locally and verify schema
npx wrangler d1 migrations apply my-database --local

# 2. Run down rollback locally
npx tsx scripts/rollback-migration.ts 0003 local

# 3. Confirm migration no longer listed as applied
npx wrangler d1 migrations list my-database --local

# 4. Re-apply should succeed cleanly
npx wrangler d1 migrations apply my-database --local
```

---

## Related

- `d1-migrations-wrangler-ci-cd.md`
- `d1-schema-versioning-wrangler-migrations.md`
- `d1-schema-drift-detection-validation.md`
- `d1-ephemeral-test-database-miniflare-teardown.md`
- `migration-rollback-strategy.md`

---

## Sources

- Wrangler D1 migrations docs: https://developers.cloudflare.com/d1/reference/migrations/
- SQLite ALTER TABLE: https://www.sqlite.org/lang_altertable.html
- Flyway baseline migration concepts: https://documentation.red-gate.com/flyway
