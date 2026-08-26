# D1 Schema Version Tracking and Migration Management

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your D1 database schema changes over time — new tables, new columns, dropped indexes — and you need a reliable, auditable process to apply those changes in order, track which migrations have run, support dry-run previews, and roll back a bad migration without guessing the current state of the database.

## Context

D1 is a managed SQLite service. Unlike traditional databases, there is no connection pool to drain before a migration: each Worker request opens a fresh SQLite connection, so migrations run in an isolated Worker invocation without blocking live traffic. The challenge is ordering, idempotency, and auditability. The pattern below uses a `schema_migrations` table as the source of truth and a dedicated migration-runner Worker endpoint.

## Solution

### 1. Migrations table

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
  version     INTEGER PRIMARY KEY,
  name        TEXT    NOT NULL,
  applied_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  checksum    TEXT    NOT NULL,
  direction   TEXT    NOT NULL DEFAULT 'up'  -- 'up' | 'down'
);
```

### 2. Migration file structure

```typescript
// src/migrations/index.ts
export interface Migration {
  version: number;
  name: string;
  up: (db: D1Database) => Promise<void>;
  down: (db: D1Database) => Promise<void>;
}

export const migrations: Migration[] = [
  {
    version: 1,
    name: 'create_articles',
    up: async (db) => {
      await db
        .prepare(`
          CREATE TABLE IF NOT EXISTS articles (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            body       TEXT NOT NULL,
            tenant_id  TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
          )
        `)
        .run();
    },
    down: async (db) => {
      await db.prepare(`DROP TABLE IF EXISTS articles`).run();
    },
  },
  {
    version: 2,
    name: 'add_articles_author',
    up: async (db) => {
      await db
        .prepare(`ALTER TABLE articles ADD COLUMN author TEXT NOT NULL DEFAULT 'unknown'`)
        .run();
    },
    down: async (db) => {
      // SQLite does not support DROP COLUMN in older versions;
      // reconstruct the table without the column
      await db.batch([
        db.prepare(`
          CREATE TABLE articles_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
          )
        `),
        db.prepare(`INSERT INTO articles_new SELECT id, title, body, tenant_id, created_at FROM articles`),
        db.prepare(`DROP TABLE articles`),
        db.prepare(`ALTER TABLE articles_new RENAME TO articles`),
      ]);
    },
  },
  {
    version: 3,
    name: 'add_articles_fts5',
    up: async (db) => {
      await db.batch([
        db.prepare(`
          CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            title, body, content='articles', content_rowid='id'
          )
        `),
        db.prepare(`
          CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
            INSERT INTO articles_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
          END
        `),
      ]);
    },
    down: async (db) => {
      await db.batch([
        db.prepare(`DROP TRIGGER IF EXISTS articles_ai`),
        db.prepare(`DROP TABLE IF EXISTS articles_fts`),
      ]);
    },
  },
];
```

### 3. Migration runner

```typescript
// src/services/migrator.ts
import { migrations, Migration } from '../migrations';
import { createHash } from 'node:crypto';

export interface MigrationStatus {
  version: number;
  name: string;
  applied: boolean;
  applied_at?: string;
}

export interface RunResult {
  applied: number[];
  skipped: number[];
  dryRun: boolean;
}

/** Compute a stable checksum for a migration's source representation */
function checksum(m: Migration): string {
  return createHash('sha256')
    .update(`${m.version}:${m.name}`)
    .digest('hex')
    .slice(0, 16);
}

/** Ensure the migrations tracking table exists */
async function ensureMigrationsTable(db: D1Database): Promise<void> {
  await db
    .prepare(`
      CREATE TABLE IF NOT EXISTS schema_migrations (
        version    INTEGER PRIMARY KEY,
        name       TEXT NOT NULL,
        applied_at TEXT NOT NULL DEFAULT (datetime('now')),
        checksum   TEXT NOT NULL,
        direction  TEXT NOT NULL DEFAULT 'up'
      )
    `)
    .run();
}

/** Return the highest applied migration version, or 0 if none */
async function currentVersion(db: D1Database): Promise<number> {
  const row = await db
    .prepare(`SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations WHERE direction = 'up'`)
    .first<{ v: number }>();
  return row?.v ?? 0;
}

/** Run all pending UP migrations in version order */
export async function runMigrations(
  db: D1Database,
  opts: { dryRun?: boolean; targetVersion?: number } = {}
): Promise<RunResult> {
  const { dryRun = false, targetVersion } = opts;

  await ensureMigrationsTable(db);
  const current = await currentVersion(db);

  const pending = migrations
    .filter((m) => m.version > current)
    .filter((m) => targetVersion === undefined || m.version <= targetVersion)
    .sort((a, b) => a.version - b.version);

  const applied: number[] = [];
  const skipped: number[] = [];

  for (const migration of pending) {
    if (dryRun) {
      console.log(`[dry-run] Would apply migration ${migration.version}: ${migration.name}`);
      skipped.push(migration.version);
      continue;
    }

    console.log(`Applying migration ${migration.version}: ${migration.name}`);
    try {
      await migration.up(db);
      await db
        .prepare(`INSERT INTO schema_migrations (version, name, checksum, direction) VALUES (?, ?, ?, 'up')`)
        .bind(migration.version, migration.name, checksum(migration))
        .run();
      applied.push(migration.version);
    } catch (err) {
      console.error(`Migration ${migration.version} failed:`, err);
      throw err; // Halt; do not apply subsequent migrations
    }
  }

  return { applied, skipped, dryRun };
}

/** Roll back the last N applied migrations */
export async function rollbackMigrations(
  db: D1Database,
  steps = 1
): Promise<number[]> {
  await ensureMigrationsTable(db);

  const rows = await db
    .prepare(`
      SELECT version, name FROM schema_migrations
      WHERE direction = 'up'
      ORDER BY version DESC
      LIMIT ?
    `)
    .bind(steps)
    .all<{ version: number; name: string }>();

  const rolledBack: number[] = [];

  for (const row of rows.results) {
    const migration = migrations.find((m) => m.version === row.version);
    if (!migration) {
      throw new Error(`No migration definition found for version ${row.version}`);
    }

    console.log(`Rolling back migration ${row.version}: ${row.name}`);
    await migration.down(db);
    await db
      .prepare(`
        INSERT INTO schema_migrations (version, name, checksum, direction)
        VALUES (?, ?, ?, 'down')
      `)
      .bind(row.version, row.name, checksum(migration))
      .run();
    rolledBack.push(row.version);
  }

  return rolledBack;
}

/** Return full migration status */
export async function migrationStatus(
  db: D1Database
): Promise<MigrationStatus[]> {
  await ensureMigrationsTable(db);

  const applied = await db
    .prepare(`
      SELECT version, applied_at
      FROM schema_migrations
      WHERE direction = 'up'
      AND version NOT IN (
        SELECT version FROM schema_migrations WHERE direction = 'down'
      )
    `)
    .all<{ version: number; applied_at: string }>();

  const appliedMap = new Map(applied.results.map((r) => [r.version, r.applied_at]));

  return migrations.map((m) => ({
    version: m.version,
    name: m.name,
    applied: appliedMap.has(m.version),
    applied_at: appliedMap.get(m.version),
  }));
}
```

### 4. Migration Worker handler

```typescript
// src/handlers/migrate.ts
import { runMigrations, rollbackMigrations, migrationStatus } from '../services/migrator';

export interface Env {
  DB: D1Database;
  MIGRATION_SECRET: string;  // KV or env secret
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Guard: only allow authenticated migration requests
    const auth = request.headers.get('x-migration-secret');
    if (auth !== env.MIGRATION_SECRET) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const url = new URL(request.url);

    // GET /migrate/status
    if (url.pathname === '/migrate/status' && request.method === 'GET') {
      const status = await migrationStatus(env.DB);
      return Response.json({ migrations: status });
    }

    // POST /migrate/up?dry_run=true&target=3
    if (url.pathname === '/migrate/up' && request.method === 'POST') {
      const dryRun = url.searchParams.get('dry_run') === 'true';
      const target = url.searchParams.has('target')
        ? parseInt(url.searchParams.get('target')!, 10)
        : undefined;
      const result = await runMigrations(env.DB, { dryRun, targetVersion: target });
      return Response.json(result);
    }

    // POST /migrate/down?steps=1
    if (url.pathname === '/migrate/down' && request.method === 'POST') {
      const steps = parseInt(url.searchParams.get('steps') ?? '1', 10);
      const rolled = await rollbackMigrations(env.DB, steps);
      return Response.json({ rolledBack: rolled });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

### 5. Dry-run via wrangler

```bash
# Preview what would be applied
curl -X POST https://api.example project.internal/migrate/up?dry_run=true \
  -H 'x-migration-secret: <secret>'

# Apply all pending migrations
curl -X POST https://api.example project.internal/migrate/up \
  -H 'x-migration-secret: <secret>'

# Roll back the last migration
curl -X POST https://api.example project.internal/migrate/down?steps=1 \
  -H 'x-migration-secret: <secret>'

# Check current status
curl https://api.example project.internal/migrate/status \
  -H 'x-migration-secret: <secret>'
```

## Implementation Details

- Migration versions are integers, not timestamps. Sequential integers (`1, 2, 3`) are easier to order, audit, and reference in code reviews than 14-digit timestamp prefixes.
- The `schema_migrations` table records both UP and DOWN events. The current effective version is `MAX(version) WHERE direction='up' AND version NOT IN (SELECT version WHERE direction='down')`. This gives a full audit trail.
- `down` migrations for SQLite often require the copy-rename pattern because SQLite supports `DROP COLUMN` only from version 3.35.0, and `ADD COLUMN` is the only `ALTER TABLE` operation that is broadly safe.
- The migration runner halts on first failure and does not apply subsequent migrations. This prevents a partially-applied migration from leaving the schema in an inconsistent state.
- `MIGRATION_SECRET` should be stored in a Cloudflare Worker secret (`wrangler secret put MIGRATION_SECRET`), not in `wrangler.toml`.

## Anti-patterns

- **Applying migrations on every request** — Running the migration check on every Worker request adds latency and risks race conditions. Run migrations explicitly as a deploy step.
- **Mutating migration files after they are applied** — A migration that has been applied to production must not be modified. Create a new migration instead.
- **Using timestamps as version numbers** — `20240824120000` is harder to read and sequence than `42`. Use sequential integers.
- **No down migration** — Always write a `down` function, even if it is a no-op stub. A rollback without a `down` is not a rollback.
- **DDL inside transactions you expect to roll back** — SQLite auto-commits most DDL statements. Do not assume a failed migration automatically undoes previous DDL in the same batch.

## Gotchas

- D1 does not expose explicit transaction control (`BEGIN`/`COMMIT`) in the HTTP API used by Workers. Each `db.prepare().run()` is its own implicit transaction. Use `db.batch()` for atomicity within a single batch.
- `ALTER TABLE ... ADD COLUMN` in SQLite cannot add a column with a non-constant default that references functions like `datetime('now')`. Add the column with a NULL default, then backfill.
- The `schema_migrations` table must be created before any migration references it. The `ensureMigrationsTable()` call at the start of every runner function guarantees this.
- When running migrations via `wrangler d1 execute --file`, the SQL file is executed outside the Worker runtime, so TypeScript migration logic does not apply. Reserve `wrangler d1 execute` for emergency hotfixes only.

## Verification

```bash
# Confirm no migrations applied yet
curl https://api.example project.internal/migrate/status -H 'x-migration-secret: <secret>'
# All migrations show applied: false

# Dry run
curl -X POST 'https://api.example project.internal/migrate/up?dry_run=true' \
  -H 'x-migration-secret: <secret>'
# Shows which migrations would be applied; schema_migrations unchanged

# Apply
curl -X POST https://api.example project.internal/migrate/up -H 'x-migration-secret: <secret>'
# { applied: [1, 2, 3], skipped: [], dryRun: false }

# Verify via D1 console
npx wrangler d1 execute example project-db --command 'SELECT * FROM schema_migrations;'
```

## Related

- `documentation/categories/database/d1-full-text-search-fts5.md` — FTS5 setup as a migration (version 3 example)
- `documentation/categories/database/d1-json-column-queries.md` — adding expression indexes via migrations
- `documentation/categories/database/d1-row-level-security-pattern.md` — tenant_id column added via migration

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://www.sqlite.org/lang_altertable.html
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
