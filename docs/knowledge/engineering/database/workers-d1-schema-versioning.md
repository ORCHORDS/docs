# D1 Schema Versioning and Migration Management

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers project using D1 grows beyond its initial schema. Engineers need to alter tables, add columns, create indexes, and drop legacy fields without wiping data or deploying broken Workers. Ad-hoc `ALTER TABLE` statements executed by hand diverge across preview and production databases and are impossible to reproduce or audit.

## Context

D1 runs SQLite under the hood. SQLite's `ALTER TABLE` support is limited (no `DROP COLUMN` before SQLite 3.35, no `RENAME COLUMN` before 3.25), so migrations often rely on the create-copy-drop pattern. D1 does not provide a native migration runner, so teams must build their own. The Worker startup path (the `scheduled` or a one-time init fetch handler) is the right place to apply pending migrations because it runs in the same execution context as all other D1 queries.

## Solution

```typescript
// src/migrations/runner.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface Migration {
  version: number;
  name: string;
  up: string;
  down?: string;
}

// Ordered list of all migrations — never reorder or delete.
export const MIGRATIONS: Migration[] = [
  {
    version: 1,
    name: 'create_users_table',
    up: `
      CREATE TABLE IF NOT EXISTS users (
        id          TEXT PRIMARY KEY,
        email       TEXT NOT NULL UNIQUE,
        created_at  INTEGER NOT NULL DEFAULT (unixepoch())
      );
    `,
    down: `DROP TABLE IF EXISTS users;`,
  },
  {
    version: 2,
    name: 'add_display_name_to_users',
    up: `ALTER TABLE users ADD COLUMN display_name TEXT;`,
    down: `
      -- SQLite <3.35 workaround: recreate table without the column
      CREATE TABLE users_backup AS SELECT id, email, created_at FROM users;
      DROP TABLE users;
      ALTER TABLE users_backup RENAME TO users;
    `,
  },
  {
    version: 3,
    name: 'create_posts_table',
    up: `
      CREATE TABLE IF NOT EXISTS posts (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL REFERENCES users(id),
        title       TEXT NOT NULL,
        body        TEXT NOT NULL,
        created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
        updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
      );
      CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);
    `,
    down: `DROP TABLE IF EXISTS posts;`,
  },
];

// Bootstrap the versions table once.
const BOOTSTRAP_SQL = `
  CREATE TABLE IF NOT EXISTS schema_versions (
    version     INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    applied_at  INTEGER NOT NULL DEFAULT (unixepoch())
  );
`;

export async function getCurrentVersion(db: D1Database): Promise<number> {
  const row = await db
    .prepare('SELECT MAX(version) AS v FROM schema_versions')
    .first<{ v: number | null }>();
  return row?.v ?? 0;
}

export async function runMigrations(
  db: D1Database,
  options: { dryRun?: boolean } = {}
): Promise<{ applied: Migration[]; skipped: Migration[] }> {
  // Ensure the versions table exists.
  await db.exec(BOOTSTRAP_SQL);

  const current = await getCurrentVersion(db);
  const pending = MIGRATIONS.filter((m) => m.version > current);

  if (options.dryRun) {
    console.log(
      `[migrations] dry-run: ${pending.length} pending migration(s):`,
      pending.map((m) => `v${m.version} ${m.name}`)
    );
    return { applied: [], skipped: pending };
  }

  const applied: Migration[] = [];

  for (const migration of pending) {
    console.log(`[migrations] applying v${migration.version}: ${migration.name}`);

    // Execute the migration SQL and record it atomically.
    await db.batch([
      db.prepare(migration.up),
      db.prepare(
        'INSERT INTO schema_versions (version, name) VALUES (?, ?)'
      ).bind(migration.version, migration.name),
    ]);

    applied.push(migration);
    console.log(`[migrations] v${migration.version} applied.`);
  }

  return { applied, skipped: [] };
}

export async function rollbackMigration(
  db: D1Database,
  targetVersion: number
): Promise<void> {
  await db.exec(BOOTSTRAP_SQL);
  const current = await getCurrentVersion(db);

  // Roll back from current down to targetVersion + 1.
  const toRollback = MIGRATIONS.filter(
    (m) => m.version > targetVersion && m.version <= current
  ).sort((a, b) => b.version - a.version); // descending

  for (const migration of toRollback) {
    if (!migration.down) {
      throw new Error(
        `Migration v${migration.version} has no rollback SQL.`
      );
    }
    console.log(`[migrations] rolling back v${migration.version}: ${migration.name}`);
    await db.batch([
      db.prepare(migration.down),
      db.prepare('DELETE FROM schema_versions WHERE version = ?').bind(
        migration.version
      ),
    ]);
    console.log(`[migrations] v${migration.version} rolled back.`);
  }
}

// src/index.ts  (Worker entry point)
import { runMigrations } from './migrations/runner';

export interface Env {
  DB: D1Database;
  MIGRATION_DRY_RUN?: string; // set to 'true' in wrangler.toml for CI
}

let migrationsApplied = false;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!migrationsApplied) {
      const dryRun = env.MIGRATION_DRY_RUN === 'true';
      const result = await runMigrations(env.DB, { dryRun });
      console.log(
        `[startup] migrations: ${result.applied.length} applied, ${result.skipped.length} skipped.`
      );
      if (!dryRun) migrationsApplied = true;
    }
    return new Response('OK');
  },

  // Cron trigger for CI validation: wrangler.toml crons = ["0 * * * *"]
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await runMigrations(env.DB, { dryRun: env.MIGRATION_DRY_RUN === 'true' });
  },
};
```

## Implementation Details

**`schema_versions` table** tracks every applied migration with a version number and timestamp. The table is bootstrapped with `CREATE TABLE IF NOT EXISTS` so the very first migration never fails.

**Atomic batch writes** — each migration uses `db.batch([migrationStmt, recordVersionStmt])`. D1 batch operations run in a single HTTP round-trip and are atomic within D1's eventual-consistency model, preventing a migration from being applied twice if the Worker is interrupted mid-flight.

**Module-level `migrationsApplied` flag** — Workers share V8 isolates across requests within the same instance. The flag skips the migration check on every request after the first, reducing latency. A new deployment or isolate restart re-runs the check; because migrations are idempotent (using `IF NOT EXISTS` or version gating), this is safe.

**`MIGRATION_DRY_RUN` environment variable** — set to `'true'` in a CI binding to validate that migrations exist and parse correctly without mutating the database.

**Migration ordering** — the array is the authoritative sequence. Never insert a migration into the middle of the list; always append. Version numbers must be monotonically increasing integers.

## Anti-patterns

- **Running raw DDL in application handlers** — schema changes happen at unpredictable times and can race with concurrent requests.
- **Using timestamps as version keys** — collisions and clock skew make ordering ambiguous; sequential integers are unambiguous.
- **Deleting or reordering migrations** — the runner compares `version > current`; gaps or reordering corrupt the version table.
- **Skipping `down` migrations** — rollback without `down` SQL forces a manual database restore.
- **Non-idempotent `up` SQL without `IF NOT EXISTS`** — causes hard failures on re-application.

## Gotchas

- D1 `db.batch()` is atomic per batch but does not span multiple batches. Keep each migration self-contained in one batch call.
- SQLite `ALTER TABLE` cannot drop or rename columns in older SQLite versions embedded in D1. Use the create-copy-drop workaround in `down` migrations.
- `db.exec()` accepts multiple semicolon-separated statements; `db.prepare()` does not. Use `db.exec()` for multi-statement migrations, but note it returns only the last result.
- The module-level flag only helps within a single isolate. If D1 is shared across multiple Workers, migrations may run redundantly from each Worker's first request; the `schema_versions` primary key prevents double-insertion.

## Verification

```typescript
// test/migrations.test.ts  (Vitest + unstable_dev)
import { unstable_dev } from 'wrangler';
import type { UnstableDevWorker } from 'wrangler';

let worker: UnstableDevWorker;

beforeAll(async () => {
  worker = await unstable_dev('src/index.ts', {
    experimental: { disableExperimentalWarning: true },
  });
});

afterAll(async () => { await worker.stop(); });

test('all migrations apply without error', async () => {
  const res = await worker.fetch('/');
  expect(res.status).toBe(200);
});

test('schema_versions contains all migrations', async () => {
  const res = await worker.fetch('/debug/schema-versions');
  const data = await res.json<{ versions: { version: number }[] }>();
  expect(data.versions.length).toBe(3); // update when adding migrations
});
```

Deploy to a preview environment with `wrangler d1 migrations apply DB --env preview` after adding migrations to the array.

## Related

- [workers-d1-soft-delete-pattern](workers-d1-soft-delete-pattern.md)
- [workers-d1-time-series-data](workers-d1-time-series-data.md)

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/d1/reference/migrations/
- https://www.sqlite.org/lang_altertable.html
