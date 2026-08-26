# Zero-Downtime D1 Schema Migrations During Deployment

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to alter a D1 table schema (add a column, rename a column, change a type) without taking the Worker offline. A naive `ALTER TABLE … DROP COLUMN` executed before deploying the new Worker version will break the currently-running version for the seconds or minutes it is still serving traffic. Equally, adding a NOT NULL column without a default will reject every INSERT from the old code.

## Context

- Cloudflare D1 is a SQLite-backed database attached to Workers via binding.
- Workers deployments are atomic at the script level but zero-downtime requires the *database* to remain compatible with both the old and new Worker versions simultaneously during the rollout window.
- The expand-contract pattern (also called parallel-change) solves this: first *expand* the schema so both old and new code can run against it, deploy the new code, backfill data, then *contract* by removing what the old code needed.
- D1 does not yet provide native migration versioning, so migration state must be tracked manually in a `schema_migrations` table.
- Wrangler 3.x `deploy` hooks (defined in `wrangler.toml`) execute shell commands before or after a deployment, enabling automated migration steps.

## Solution

```typescript
// scripts/migrate.ts
// Run with: npx wrangler d1 execute DB --file=migrations/<file>.sql
// Or programmatically from a migration Worker (see below)

import { D1Database } from '@cloudflare/workers-types';

export interface MigrationRecord {
  id: number;
  version: string;
  name: string;
  applied_at: string;
  checksum: string;
  rolled_back_at: string | null;
}

export interface Migration {
  version: string;
  name: string;
  up: string;   // SQL to apply
  down: string; // SQL to revert
  checksum: string;
}

// --- Migration registry ---
export const MIGRATIONS: Migration[] = [
  {
    version: '20260824001',
    name: 'add_email_verified_column',
    // EXPAND: add nullable column so old code keeps working
    up: `
      ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0;
      CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email_verified);
    `,
    // CONTRACT rollback: only safe once new column is no longer referenced
    down: `
      DROP INDEX IF EXISTS idx_users_email_verified;
      -- D1/SQLite cannot DROP COLUMN on older versions; use table rebuild:
      CREATE TABLE users_old AS SELECT id, name, email, created_at FROM users;
      DROP TABLE users;
      ALTER TABLE users_old RENAME TO users;
    `,
    checksum: 'sha256:a1b2c3d4e5f6',
  },
  {
    version: '20260824002',
    name: 'backfill_email_verified',
    up: `
      UPDATE users
      SET    email_verified = 1
      WHERE  email LIKE '%@verified.example.com'
         OR  created_at < '2025-01-01';
    `,
    down: `UPDATE users SET email_verified = 0;`,
    checksum: 'sha256:b2c3d4e5f6a1',
  },
  {
    version: '20260824003',
    name: 'make_email_verified_not_null',
    // CONTRACT: now safe — all rows have a value, new code is live
    up: `
      -- SQLite cannot ALTER COLUMN; rebuild with NOT NULL constraint
      CREATE TABLE users_new (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        email      TEXT    NOT NULL UNIQUE,
        email_verified INTEGER NOT NULL DEFAULT 0,
        created_at TEXT    NOT NULL DEFAULT (datetime('now'))
      );
      INSERT INTO users_new SELECT id, name, email, COALESCE(email_verified,0), created_at FROM users;
      DROP TABLE users;
      ALTER TABLE users_new RENAME TO users;
      CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email_verified);
    `,
    down: `SELECT 1; -- intentionally non-reversible after contract phase`,
    checksum: 'sha256:c3d4e5f6a1b2',
  },
];

// --- Migration runner (Worker-based) ---
export async function runPendingMigrations(
  db: D1Database,
  dryRun = false,
): Promise<{ applied: string[]; errors: string[] }> {
  await db.exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      version        TEXT    NOT NULL UNIQUE,
      name           TEXT    NOT NULL,
      applied_at     TEXT    NOT NULL DEFAULT (datetime('now')),
      checksum       TEXT    NOT NULL,
      rolled_back_at TEXT
    );
  `);

  const applied = await db
    .prepare('SELECT version FROM schema_migrations WHERE rolled_back_at IS NULL')
    .all<{ version: string }>();

  const appliedVersions = new Set(applied.results.map((r) => r.version));
  const pending = MIGRATIONS.filter((m) => !appliedVersions.has(m.version));

  const results: { applied: string[]; errors: string[] } = { applied: [], errors: [] };

  for (const migration of pending) {
    if (dryRun) {
      console.log(`[DRY RUN] Would apply: ${migration.version} — ${migration.name}`);
      results.applied.push(migration.version);
      continue;
    }

    try {
      // Execute migration SQL (may contain multiple statements)
      for (const stmt of migration.up.split(';').map((s) => s.trim()).filter(Boolean)) {
        await db.exec(stmt + ';');
      }

      await db
        .prepare(
          `INSERT INTO schema_migrations (version, name, checksum)
           VALUES (?, ?, ?)`,
        )
        .bind(migration.version, migration.name, migration.checksum)
        .run();

      console.log(`Applied: ${migration.version} — ${migration.name}`);
      results.applied.push(migration.version);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error(`Failed: ${migration.version} — ${msg}`);
      results.errors.push(`${migration.version}: ${msg}`);
      break; // stop on first error
    }
  }

  return results;
}

export async function rollbackMigration(
  db: D1Database,
  version: string,
): Promise<void> {
  const migration = MIGRATIONS.find((m) => m.version === version);
  if (!migration) throw new Error(`Unknown migration version: ${version}`);

  for (const stmt of migration.down.split(';').map((s) => s.trim()).filter(Boolean)) {
    await db.exec(stmt + ';');
  }

  await db
    .prepare(
      `UPDATE schema_migrations
       SET    rolled_back_at = datetime('now')
       WHERE  version = ?`,
    )
    .bind(version)
    .run();

  console.log(`Rolled back: ${version}`);
}

// --- Validation: check schema state matches expectation ---
export async function validateSchema(
  db: D1Database,
  expectedColumns: Record<string, string[]>,
): Promise<{ valid: boolean; missing: string[] }> {
  const missing: string[] = [];

  for (const [table, columns] of Object.entries(expectedColumns)) {
    const info = await db
      .prepare(`PRAGMA table_info(${table})`)
      .all<{ name: string }>();
    const existing = new Set(info.results.map((r) => r.name));
    for (const col of columns) {
      if (!existing.has(col)) missing.push(`${table}.${col}`);
    }
  }

  return { valid: missing.length === 0, missing };
}
```

```yaml
# wrangler.toml — deploy hooks
name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding     = "DB"
database_name = "orchords-prod"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Wrangler deploy hooks run in CI before/after the script upload
[deploy]
pre_deploy  = "npx tsx scripts/run-migrations.ts"
post_deploy = "npx tsx scripts/validate-schema.ts"
```

```typescript
// scripts/run-migrations.ts  (pre-deploy hook)
// Invokes the migration Worker endpoint instead of running locally
// so it runs against the real D1 binding with production credentials.

const MIGRATION_ENDPOINT =
  process.env.MIGRATION_ENDPOINT ?? 'https://orchords-api.orchords.workers.dev/__migrate';
const MIGRATION_SECRET = process.env.MIGRATION_SECRET ?? '';

async function main() {
  const res = await fetch(MIGRATION_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${MIGRATION_SECRET}`,
    },
    body: JSON.stringify({ dryRun: false }),
  });

  if (!res.ok) {
    const body = await res.text();
    console.error('Migration failed:', body);
    process.exit(1);
  }

  const data = (await res.json()) as { applied: string[]; errors: string[] };
  console.log('Applied:', data.applied);
  if (data.errors.length > 0) {
    console.error('Errors:', data.errors);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

## Implementation Details

**Expand phase** — the migration adds the new column as nullable (or with a safe default). Both the old Worker version and the new Worker version can coexist because the old code ignores unknown columns on SELECT and does not attempt to write the new column.

**Deploy phase** — Wrangler atomically swaps the Worker script. Because D1 already has the expanded schema, the new code can read and write the new column immediately.

**Backfill phase** — migration `20260824002` runs as a separate step so large tables can be updated in batches without hitting D1's 30-second timeout. For tables > 100k rows, use a Durable Object or a Cron Trigger to process in pages of 1000 rows.

**Contract phase** — only after verifying the new Worker is fully live and the old version is no longer routing traffic do you apply `20260824003`. This rebuilds the table with the final NOT NULL constraint.

**State tracking** — `schema_migrations` records every applied version, its checksum, and a rollback timestamp. The checksum prevents re-running a modified migration by accident.

**Migration Worker endpoint** — The pre-deploy script calls a protected `/__migrate` route in the *current* deployed Worker (not the new one). This route has access to the D1 binding and can safely run SQL. The route is protected by a Bearer token stored in a Worker secret.

## Anti-patterns

- Running `DROP COLUMN` before deploying the new Worker — breaks the running version during traffic.
- Adding NOT NULL without a default on a live table — breaks every INSERT from the old code.
- Mixing DDL and DML in a single migration — makes rollback harder; keep structural changes and backfills in separate versioned steps.
- Relying on `wrangler d1 migrations apply` in a local shell as the only migration path — if the CI runner has no D1 write access, the step silently skips.
- Using `db.exec()` for untrusted SQL — this endpoint must be strictly internal, authenticated by secret.

## Gotchas

- D1 SQLite does not support `ALTER TABLE … DROP COLUMN` before SQLite 3.35. The workaround is the table-rebuild pattern shown in `20260824003`.
- `db.exec()` runs the SQL in a single implicit transaction per statement — multi-statement migrations must be split on `;` and issued individually.
- D1 has a 30-second CPU budget per request; backfilling large tables must be chunked.
- `wrangler deploy` pre/post hooks are a Wrangler 3.60+ feature — pin your Wrangler version in `package.json`.
- If a migration fails mid-way, the `schema_migrations` row is not inserted, so re-running is safe, but partial DDL (e.g. a half-built table) may need manual cleanup.

## Verification

```typescript
// scripts/validate-schema.ts  (post-deploy hook)
const VALIDATE_ENDPOINT =
  process.env.MIGRATION_ENDPOINT ?? 'https://orchords-api.orchords.workers.dev/__migrate/validate';
const MIGRATION_SECRET = process.env.MIGRATION_SECRET ?? '';

async function main() {
  const res = await fetch(VALIDATE_ENDPOINT, {
    method: 'POST',
    headers: { Authorization: `Bearer ${MIGRATION_SECRET}` },
    body: JSON.stringify({
      expectedColumns: {
        users: ['id', 'name', 'email', 'email_verified', 'created_at'],
        schema_migrations: ['id', 'version', 'name', 'applied_at', 'checksum', 'rolled_back_at'],
      },
    }),
  });

  const data = (await res.json()) as { valid: boolean; missing: string[] };
  if (!data.valid) {
    console.error('Schema validation failed. Missing:', data.missing);
    process.exit(1);
  }
  console.log('Schema validation passed.');
}

main().catch((e) => { console.error(e); process.exit(1); });
```

Also verify via Wrangler CLI after each phase:

```bash
npx wrangler d1 execute orchords-prod \
  --command "SELECT version, name, applied_at FROM schema_migrations ORDER BY id DESC LIMIT 10;"
```

## Related

- `documentation/docs/policies/deploy/workers-deployment-approval-gates.md` — gating migrations behind manual approval
- `documentation/docs/policies/deploy/workers-version-pinning-gradual-rollout.md` — coordinating schema changes with gradual traffic rollout
- Cloudflare D1 documentation: Migrations
- Martin Fowler — Parallel Change (expand-contract) pattern

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/wrangler/configuration/#deploy
- https://martinfowler.com/bliki/ParallelChange.html
- https://sqlite.org/lang_altertable.html
