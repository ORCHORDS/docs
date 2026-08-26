# D1 Migration Rollback Testing for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You apply a D1 migration, realise it introduced a bug, and need to roll back. The rollback itself works, but you have no tests to prove that the data is intact and the Worker still serves correct responses afterward. Without a rollback test suite, you are flying blind during an incident.

## Context

D1 does not have native point-in-time rollback (as of 2026). Rollback is achieved by running a reverse migration SQL file (`down.sql`) via `wrangler d1 execute`. This article shows how to test the full cycle — apply, smoke-test, rollback, verify — locally with Miniflare and in CI with a real D1 preview database.

---

## Section 1 — Migration file structure

```
db/
  migrations/
    0001_create_users.up.sql
    0001_create_users.down.sql
    0002_add_display_name.up.sql
    0002_add_display_name.down.sql
```

```sql
-- db/migrations/0002_add_display_name.up.sql
ALTER TABLE users ADD COLUMN display_name TEXT;
CREATE INDEX idx_users_display_name ON users (display_name);
```

```sql
-- db/migrations/0002_add_display_name.down.sql
DROP INDEX IF EXISTS idx_users_display_name;
-- SQLite does not support DROP COLUMN before 3.35; wrangler bundles 3.39+
ALTER TABLE users DROP COLUMN display_name;
```

## Section 2 — Programmatic migration runner (test helper)

```ts
// tests/helpers/d1-migrations.ts
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

export interface Migration {
  version: number;
  name: string;
  up: string;
  down: string;
}

const MIGRATIONS_DIR = join(process.cwd(), 'db/migrations');

export function loadMigrations(): Migration[] {
  const files = readdirSync(MIGRATIONS_DIR).sort();
  const upFiles = files.filter((f) => f.endsWith('.up.sql'));

  return upFiles.map((upFile) => {
    const match = upFile.match(/^(\d+)_(.+)\.up\.sql$/);
    if (!match) throw new Error(`Unexpected migration filename: ${upFile}`);
    const [, versionStr, name] = match;
    const downFile = `${versionStr}_${name}.down.sql`;
    return {
      version: parseInt(versionStr, 10),
      name,
      up: readFileSync(join(MIGRATIONS_DIR, upFile), 'utf8'),
      down: readFileSync(join(MIGRATIONS_DIR, downFile), 'utf8'),
    };
  });
}

export async function applyMigration(
  db: D1Database,
  migration: Migration
): Promise<void> {
  // Split on semicolons; D1 batch handles multi-statement migrations
  const statements = migration.up
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean);
  await db.batch(statements.map((sql) => db.prepare(sql)));
  await db
    .prepare(
      `INSERT INTO _migrations (version, name, applied_at)
       VALUES (?, ?, datetime('now'))`
    )
    .bind(migration.version, migration.name)
    .run();
}

export async function rollbackMigration(
  db: D1Database,
  migration: Migration
): Promise<void> {
  const statements = migration.down
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean);
  await db.batch(statements.map((sql) => db.prepare(sql)));
  await db
    .prepare(`DELETE FROM _migrations WHERE version = ?`)
    .bind(migration.version)
    .run();
}

export async function bootstrapMigrationsTable(
  db: D1Database
): Promise<void> {
  await db
    .prepare(
      `CREATE TABLE IF NOT EXISTS _migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL
      )`
    )
    .run();
}
```

## Section 3 — Apply, smoke-test, rollback, verify

```ts
// tests/migrations/0002-rollback.test.ts
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll } from 'vitest';
import {
  loadMigrations,
  applyMigration,
  rollbackMigration,
  bootstrapMigrationsTable,
} from '../helpers/d1-migrations';

const migrations = loadMigrations();
const migration0001 = migrations.find((m) => m.version === 1)!;
const migration0002 = migrations.find((m) => m.version === 2)!;

describe('Migration 0002 rollback', () => {
  beforeAll(async () => {
    await bootstrapMigrationsTable(env.DB);
    // Apply baseline migration
    await applyMigration(env.DB, migration0001);
    // Seed some pre-migration data
    await env.DB.prepare(
      `INSERT INTO users (id, email) VALUES (1, 'alice@example.com'), (2, 'bob@example.com')`
    ).run();
  });

  it('applies migration 0002 successfully', async () => {
    await applyMigration(env.DB, migration0002);
    const row = await env.DB.prepare(
      `SELECT display_name FROM users WHERE id = 1`
    ).first<{ display_name: string | null }>();
    // Column exists, value is NULL before population
    expect(row).not.toBeNull();
    expect(row!.display_name).toBeNull();
  });

  it('smoke test: Worker returns new display_name field after migration', async () => {
    await env.DB.prepare(
      `UPDATE users SET display_name = 'Alice' WHERE id = 1`
    ).run();
    const res = await SELF.fetch('https://example.com/users/1');
    expect(res.status).toBe(200);
    const body = await res.json<{ displayName: string }>();
    expect(body.displayName).toBe('Alice');
  });

  it('rolls back migration 0002 without data loss on other columns', async () => {
    await rollbackMigration(env.DB, migration0002);

    // Original columns still intact
    const row = await env.DB.prepare(
      `SELECT id, email FROM users WHERE id = 1`
    ).first<{ id: number; email: string }>();
    expect(row).toEqual({ id: 1, email: 'alice@example.com' });

    // display_name column is gone
    await expect(
      env.DB.prepare(`SELECT display_name FROM users WHERE id = 1`).first()
    ).rejects.toThrow();
  });

  it('Worker still serves 200 after rollback (v1 response shape)', async () => {
    const res = await SELF.fetch('https://example.com/users/1');
    expect(res.status).toBe(200);
    const body = await res.json<Record<string, unknown>>();
    expect(body).toHaveProperty('email', 'alice@example.com');
    expect(body).not.toHaveProperty('displayName');
  });

  it('_migrations table reflects the rollback', async () => {
    const row = await env.DB.prepare(
      `SELECT version FROM _migrations WHERE version = 2`
    ).first();
    expect(row).toBeNull(); // rolled back = removed from _migrations
  });

  it('row count is preserved — no data was deleted', async () => {
    const result = await env.DB.prepare(
      `SELECT COUNT(*) as cnt FROM users`
    ).first<{ cnt: number }>();
    expect(result!.cnt).toBe(2);
  });
});
```

## Section 4 — CI pipeline integration with real D1 preview database

```yaml
# .github/workflows/migration-rollback.yml
name: D1 Migration Rollback Test

on:
  pull_request:
    paths:
      - 'db/migrations/**'

jobs:
  rollback-test:
    runs-on: ubuntu-latest
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      D1_DATABASE_ID: ${{ secrets.D1_PREVIEW_DB_ID }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - run: npm ci

      - name: Apply migrations to preview D1
        run: |
          npx wrangler d1 migrations apply --env preview ${{ env.D1_DATABASE_ID }}

      - name: Run smoke tests against preview
        run: npx vitest run tests/migrations/ --mode preview

      - name: Roll back last migration via wrangler
        if: failure()
        run: |
          # Determine last applied migration version
          LAST=$(npx wrangler d1 execute ${{ env.D1_DATABASE_ID }} \
            --command "SELECT version FROM _migrations ORDER BY version DESC LIMIT 1" \
            --json | jq -r '.[0].results[0].version')
          PADDED=$(printf '%04d' $LAST)
          npx wrangler d1 execute ${{ env.D1_DATABASE_ID }} \
            --file db/migrations/${PADDED}_*.down.sql

      - name: Verify data integrity post-rollback
        if: failure()
        run: npx vitest run tests/migrations/post-rollback-integrity.test.ts --mode preview
```

## Anti-patterns

- **Writing `down.sql` that truncates tables** — always restore the schema, never destroy data. Use `ALTER TABLE DROP COLUMN`, `DROP INDEX`, `DROP TABLE` only when the table itself was created in the `up.sql`.
- **Testing only `up.sql`** — the rollback path is what you run during an incident. Invest the same testing effort in both directions.
- **Sharing a preview D1 between PRs** — concurrent PRs applying incompatible migrations corrupt each other's test runs. Use ephemeral D1 databases created per-PR via the Cloudflare API.

## Gotchas

- SQLite's `ALTER TABLE DROP COLUMN` requires SQLite 3.35+. Wrangler bundles 3.39+, but local SQLite (macOS default) may be older. Always test `down.sql` with `wrangler d1 execute --local`.
- D1 `batch()` is all-or-nothing within a single batch, but a migration with multiple batches is not atomic. Keep each migration's `up.sql` as a single batch where possible.
- `_migrations` table must be created by your bootstrap step before the first migration, or `applied_at` tracking will fail.

## Verification

```bash
# Local: run full migration rollback test suite
npx vitest run tests/migrations/

# Apply and rollback against local D1
npx wrangler d1 migrations apply DB --local
npx wrangler d1 execute DB --local --file db/migrations/0002_add_display_name.down.sql
npx wrangler d1 execute DB --local --command "SELECT * FROM users LIMIT 5"
```

## Related

- `documentation/docs/policies/testing/workers-api-versioning-backward-compat-test.md`
- `documentation/d1/workers-d1-schema-versioning.md`
- `documentation/ci/workers-ephemeral-d1-per-pr.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://www.sqlite.org/lang_altertable.html
