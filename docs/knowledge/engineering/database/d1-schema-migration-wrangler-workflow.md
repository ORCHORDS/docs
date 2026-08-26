# Structured D1 Schema Migration Workflow with Wrangler

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your D1 database schema is evolving and ad-hoc `wrangler d1 execute` commands are becoming hard to track across environments. You need a repeatable, CI-safe migration workflow that keeps a history of applied changes, supports dry-runs before deployment, and provides a rollback strategy when something goes wrong.

---

## Context

Wrangler v3+ ships with a built-in migration system for D1: sequential SQL files in a `migrations/` directory are applied in order and tracked in a `d1_migrations` system table that D1 manages automatically. Each file is named with a zero-padded numeric prefix (`0001_`, `0002_`, …) so lexicographic ordering equals application order. `wrangler d1 migrations apply` is idempotent — it skips already-applied migrations. A `--dry-run` flag prints the SQL that would run without touching the database, making it safe to validate in CI before a production deploy. Rollback is handled via compensating (forward) migrations rather than destructive `DOWN` migrations, which avoids state-machine complexity.

---

## Section 1 — D1 Schema

```sql
-- migrations/0001_initial_schema.sql
CREATE TABLE IF NOT EXISTS articles (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id   TEXT    NOT NULL,
  title      TEXT    NOT NULL,
  body       TEXT    NOT NULL,
  published  INTEGER NOT NULL DEFAULT 0,
  created_at TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_articles_owner ON articles(owner_id);

-- migrations/0002_add_tags.sql
ALTER TABLE articles ADD COLUMN tags TEXT;     -- JSON array, nullable

-- migrations/0003_add_slug.sql
ALTER TABLE articles ADD COLUMN slug TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_slug ON articles(slug)
  WHERE slug IS NOT NULL;

-- migrations/0004_rollback_slug.sql  (compensating migration example)
-- If 0003 causes issues, apply this to remove the slug feature:
-- DROP INDEX IF EXISTS idx_articles_slug;
-- Note: SQLite does not support DROP COLUMN in D1 as of 2024.
-- Strategy: stop writing slug, treat it as deprecated, add a migration
-- comment marking it unused.
-- ALTER TABLE articles RENAME COLUMN slug TO slug_deprecated;
```

---

## Section 2 — Worker implementation

```typescript
// src/db/migrations.ts
// Runtime migration status check — useful for health endpoints.

import { Env } from '../types';

interface MigrationRecord {
  id: number;
  name: string;
  applied_at: string;
}

/**
 * Returns the list of migrations already applied, as recorded
 * in D1's internal d1_migrations table.
 */
export async function listAppliedMigrations(
  env: Env
): Promise<MigrationRecord[]> {
  const { results } = await env.DB.prepare(
    `SELECT id, name, applied_at FROM d1_migrations ORDER BY id ASC`
  ).all<MigrationRecord>();
  return results ?? [];
}

/**
 * Returns the name of the most recently applied migration.
 * Useful for version headers or monitoring dashboards.
 */
export async function currentSchemaVersion(
  env: Env
): Promise<string | null> {
  const row = await env.DB.prepare(
    `SELECT name FROM d1_migrations ORDER BY id DESC LIMIT 1`
  ).first<{ name: string }>();
  return row?.name ?? null;
}

// Health endpoint handler
export async function handleDbHealth(
  _request: Request,
  env: Env
): Promise<Response> {
  const [migrations, version] = await Promise.all([
    listAppliedMigrations(env),
    currentSchemaVersion(env),
  ]);

  return Response.json({
    ok: true,
    schema_version: version,
    migrations_applied: migrations.length,
    migrations,
  });
}
```

---

## Section 3 — Query / Migration helper

```bash
# wrangler.toml — declare the migrations directory
# [[d1_databases]]
# binding = "DB"
# database_name = "my-database"
# database_id = "<uuid>"
# migrations_dir = "migrations"   # <-- tells wrangler where to look

# List pending migrations (does not apply)
wrangler d1 migrations list DB --remote

# Dry-run: print SQL that would be applied without executing it
wrangler d1 migrations apply DB --remote --dry-run

# Apply all pending migrations (production)
wrangler d1 migrations apply DB --remote

# Apply to local dev database (uses local SQLite replica)
wrangler d1 migrations apply DB --local

# Create a new numbered migration file
# (wrangler generates the next sequential filename)
wrangler d1 migrations create DB "add_comments_table"
# -> creates migrations/0005_add_comments_table.sql
```

```typescript
// scripts/ci-migrate.ts — run from GitHub Actions before wrangler deploy
import { execSync } from 'child_process';

const DRY_RUN = process.env.CI_DRY_RUN === 'true';

function run(cmd: string): void {
  console.log(`> ${cmd}`);
  execSync(cmd, { stdio: 'inherit' });
}

// Step 1: validate with dry-run (always)
run('wrangler d1 migrations apply DB --remote --dry-run');

if (!DRY_RUN) {
  // Step 2: apply for real
  run('wrangler d1 migrations apply DB --remote');
  console.log('Migrations applied successfully.');
} else {
  console.log('Dry-run only — no changes applied.');
}
```

---

## Anti-patterns

- **Editing an already-applied migration file** — D1 tracks filenames, not content hashes. Changing an applied file does nothing and creates a silent divergence between the file and the actual schema. Always create a new numbered file.
- **Using `wrangler d1 execute` for schema changes** — Ad-hoc `execute` commands bypass the migration tracker so the `d1_migrations` table never records them. Use `migrations apply` exclusively for DDL.
- **Destructive DOWN migrations** — Dropping tables or columns to undo a migration risks data loss. Prefer compensating forward migrations that rename or deprecate columns.
- **Not running `--dry-run` in CI** — Skipping the dry-run step means schema errors surface only after deploy starts. A dry-run costs nothing and catches syntax errors early.
- **Skipping `migrations_dir` in `wrangler.toml`** — Without this key, `wrangler d1 migrations` commands default to `./migrations` but an explicit declaration makes the intent clear and prevents surprises when the directory is renamed.

---

## Gotchas

- D1 creates the `d1_migrations` table on the first `migrations apply` call; querying it before that throws `no such table`.
- SQLite (and D1) does not support `DROP COLUMN` via standard `ALTER TABLE` — use a `CREATE TABLE + INSERT + DROP + RENAME` sequence or accept the column as permanently present.
- Migration filenames are sorted lexicographically by wrangler; a file named `10_` sorts before `9_` — always zero-pad (e.g. `0010_`).
- The `--local` flag writes to a local SQLite file (`.wrangler/state/`), not the remote D1 database; always verify with `--remote` before production deploys.
- Parallel migrations from multiple branches can cause numbering conflicts in long-lived feature branches. Use a shared migration counter (PR convention) or timestamp-based prefixes (`20260824_`) for teams.

---

## Verification

```bash
# List all applied migrations
wrangler d1 execute DB --remote --command \
  "SELECT id, name, applied_at FROM d1_migrations ORDER BY id;"

# Confirm a specific table exists post-migration
wrangler d1 execute DB --remote --command \
  "SELECT name FROM sqlite_master WHERE type='table' AND name='articles';"

# Dry-run before every production deploy (add to CI pipeline)
wrangler d1 migrations apply DB --remote --dry-run
```

---

## Related

- `d1-composite-indexes-query-optimization.md`
- `d1-batch-transactions-atomic-writes.md`
- `d1-row-level-security-workers.md`

---

## Sources

- Cloudflare D1 Migrations — https://developers.cloudflare.com/d1/reference/migrations/
- Wrangler CLI D1 reference — https://developers.cloudflare.com/workers/wrangler/commands/#d1
- SQLite ALTER TABLE — https://www.sqlite.org/lang_altertable.html
