# Miniflare D1 Migration Testing Up-Down

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare Workers project uses D1 with Wrangler-managed migrations. After adding a new migration, tests break because the local D1 schema is out of sync. You also need to verify that rollback migrations (`down` scripts) correctly reverse schema changes without data loss, and that your migration history table stays consistent across repeated up/down cycles—all without touching the remote D1 database.

## Context

Wrangler applies migrations forward-only using the `_cf_KV` migrations table. There is no built-in `wrangler d1 migrations down` command. For testing up-down cycles, the approach is to use Miniflare's in-memory D1 (via `@cloudflare/vitest-pool-workers`) and manually apply and revert SQL scripts. Tests verify schema state by querying `PRAGMA table_info()`, `PRAGMA foreign_key_list()`, and the migrations registry table itself. This catches: destructive column drops, missing index creation, broken FK constraints, and migration idempotency failures.

---

## 1. Migration File Conventions

```
migrations/
  0001_create_users.sql
  0001_create_users.down.sql
  0002_add_orders.sql
  0002_add_orders.down.sql
  0003_add_product_fk.sql
  0003_add_product_fk.down.sql
```

```sql
-- migrations/0001_create_users.sql
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS _migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at INTEGER NOT NULL DEFAULT (unixepoch())
);

INSERT OR IGNORE INTO _migrations (version, name) VALUES (1, '0001_create_users');
```

```sql
-- migrations/0001_create_users.down.sql
DROP TABLE IF EXISTS users;
DELETE FROM _migrations WHERE version = 1;
```

---

## 2. Migration Runner Helper

```typescript
// tests/helpers/migration-runner.ts
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import type { D1Database } from '@cloudflare/workers-types';

const MIGRATIONS_DIR = join(process.cwd(), 'migrations');

function getMigrationFiles(direction: 'up' | 'down'): string[] {
  const suffix = direction === 'down' ? '.down.sql' : '.sql';
  const files = readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith(suffix) && !f.includes('.down.sql') === (direction === 'up'))
    .sort();

  return direction === 'down' ? files.reverse() : files;
}

export async function runMigrations(
  db: D1Database,
  direction: 'up' | 'down',
  count?: number
): Promise<string[]> {
  const files = getMigrationFiles(direction).slice(0, count ?? Infinity);
  const applied: string[] = [];

  for (const file of files) {
    const sql = readFileSync(join(MIGRATIONS_DIR, file), 'utf8');
    const statements = sql
      .split(';')
      .map((s) => s.trim())
      .filter(Boolean);

    const batch = statements.map((s) => db.prepare(s));
    await db.batch(batch);
    applied.push(file);
  }

  return applied;
}

export async function getAppliedMigrations(db: D1Database): Promise<number[]> {
  try {
    const result = await db
      .prepare('SELECT version FROM _migrations ORDER BY version')
      .all<{ version: number }>();
    return result.results.map((r) => r.version);
  } catch {
    return []; // _migrations table doesn't exist yet
  }
}
```

---

## 3. Up Migration Tests

```typescript
// tests/migrations/migrations-up.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';
import { runMigrations, getAppliedMigrations } from '../helpers/migration-runner';

describe('D1 up migrations', () => {
  beforeEach(async () => {
    // Start from a clean schema each test
    await env.DB.exec('DROP TABLE IF EXISTS order_items');
    await env.DB.exec('DROP TABLE IF EXISTS orders');
    await env.DB.exec('DROP TABLE IF EXISTS users');
    await env.DB.exec('DROP TABLE IF EXISTS _migrations');
  });

  it('applies migration 0001 and creates users table', async () => {
    await runMigrations(env.DB, 'up', 1);

    const info = await env.DB
      .prepare("PRAGMA table_info('users')")
      .all<{ name: string; type: string; notnull: number }>();

    const columns = info.results.map((r) => r.name);
    expect(columns).toContain('id');
    expect(columns).toContain('email');
    expect(columns).toContain('created_at');
  });

  it('records migration version in _migrations table', async () => {
    await runMigrations(env.DB, 'up', 1);
    const applied = await getAppliedMigrations(env.DB);
    expect(applied).toContain(1);
  });

  it('applies all migrations sequentially without error', async () => {
    const files = await runMigrations(env.DB, 'up');
    expect(files.length).toBeGreaterThan(0);

    const applied = await getAppliedMigrations(env.DB);
    expect(applied).toEqual(
      Array.from({ length: applied.length }, (_, i) => i + 1)
    );
  });

  it('applying the same migration twice is idempotent (IF NOT EXISTS)', async () => {
    await runMigrations(env.DB, 'up', 1);
    await expect(runMigrations(env.DB, 'up', 1)).resolves.not.toThrow();
  });
});
```

---

## 4. Down Migration Tests

```typescript
// tests/migrations/migrations-down.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';
import { runMigrations, getAppliedMigrations } from '../helpers/migration-runner';

describe('D1 down migrations', () => {
  beforeEach(async () => {
    // Apply all migrations before each test
    await env.DB.exec('DROP TABLE IF EXISTS order_items');
    await env.DB.exec('DROP TABLE IF EXISTS orders');
    await env.DB.exec('DROP TABLE IF EXISTS users');
    await env.DB.exec('DROP TABLE IF EXISTS _migrations');
    await runMigrations(env.DB, 'up');
  });

  it('rollback 0002 removes orders table', async () => {
    await runMigrations(env.DB, 'down', 1);

    const tables = await env.DB
      .prepare("SELECT name FROM sqlite_master WHERE type='table'")
      .all<{ name: string }>();

    const tableNames = tables.results.map((r) => r.name);
    expect(tableNames).not.toContain('orders');
    expect(tableNames).toContain('users'); // earlier migration still applied
  });

  it('rollback removes migration version from registry', async () => {
    const before = await getAppliedMigrations(env.DB);
    await runMigrations(env.DB, 'down', 1);
    const after = await getAppliedMigrations(env.DB);

    expect(after.length).toBe(before.length - 1);
    expect(after).not.toContain(Math.max(...before));
  });

  it('full rollback leaves clean schema', async () => {
    await runMigrations(env.DB, 'down'); // roll back everything

    const tables = await env.DB
      .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
      .all<{ name: string }>();

    expect(tables.results.map((r) => r.name)).toHaveLength(0);
  });
});
```

---

## 5. Up-Down-Up Round-trip Test

```typescript
// tests/migrations/migrations-roundtrip.test.ts
import { env } from 'cloudflare:test';
import { it, expect, beforeEach } from 'vitest';
import { runMigrations, getAppliedMigrations } from '../helpers/migration-runner';

beforeEach(async () => {
  await env.DB.exec('DROP TABLE IF EXISTS order_items');
  await env.DB.exec('DROP TABLE IF EXISTS orders');
  await env.DB.exec('DROP TABLE IF EXISTS users');
  await env.DB.exec('DROP TABLE IF EXISTS _migrations');
});

it('up → down → up cycle produces consistent schema', async () => {
  // First up
  await runMigrations(env.DB, 'up');
  const afterFirstUp = await getAppliedMigrations(env.DB);

  // Insert test data to verify data survival (or expected loss)
  await env.DB.prepare("INSERT INTO users (id, email) VALUES ('u1', 'a@b.com')").run();

  // Down
  await runMigrations(env.DB, 'down');
  const afterDown = await getAppliedMigrations(env.DB);
  expect(afterDown).toHaveLength(0);

  // Second up
  await runMigrations(env.DB, 'up');
  const afterSecondUp = await getAppliedMigrations(env.DB);

  expect(afterSecondUp).toEqual(afterFirstUp);

  // Verify schema is identical by comparing column sets
  const cols = await env.DB
    .prepare("PRAGMA table_info('users')")
    .all<{ name: string }>();
  expect(cols.results.map((c) => c.name)).toEqual(['id', 'email', 'created_at']);
});
```

---

## Anti-patterns

- **Running migration tests against the remote D1**: Down migrations on a remote database delete real schema objects. Always use Miniflare's in-process D1.
- **Testing migrations as part of unit tests**: Migration tests are integration tests and should run in a separate Vitest project to avoid polluting unit test isolation.
- **Using `db.exec()` for multi-statement scripts without splitting**: `db.exec()` in the Workers binding may not handle multi-statement SQL consistently. Split on `;` and use `db.batch()`.
- **Not testing the down path**: Most teams test only the up direction. The down path breaks silently until a rollback is needed in production.
- **Generating `DROP TABLE` down migrations without data backups**: Down migrations that drop columns permanently destroy data. Add data-preservation steps (e.g., copy to a backup table) in the down script during testing.

---

## Gotchas

- `PRAGMA table_info()` returns SQLite internal metadata. Column order in the result matches DDL declaration order, not alphabetical.
- Wrangler's migrations table is named `_cf_KV` in remote D1, not a custom `_migrations` table. For local Miniflare tests, use your own registry table to avoid conflicts with Wrangler state.
- SQLite (used by D1) does not support `DROP COLUMN` in older versions. D1 runs SQLite 3.40+, which supports it, but Miniflare may use an older bundled version. Check `SELECT sqlite_version()`.
- `IF NOT EXISTS` and `OR IGNORE` are essential for idempotent migrations. Without them, re-running a migration throws `table already exists`.
- D1's `batch()` runs statements in the same transaction; a failing statement rolls back all preceding statements in the batch. Structure batches accordingly.

---

## Verification

```bash
# Run migration tests only
npx vitest run tests/migrations/

# Run round-trip test with verbose output
npx vitest run tests/migrations/migrations-roundtrip.test.ts --reporter=verbose

# Check SQLite version inside Miniflare
npx vitest run -t 'sqlite version' tests/migrations/
```

---

## Related

- `miniflare-d1-integration-testing.md`
- `d1-test-fixtures-wrangler-seed.md`
- `database-migration-testing.md`
- `vitest-cloudflare-pool-workers.md`
- `transactional-test-rollback.md`

---

## Sources

- Wrangler D1 migrations docs: https://developers.cloudflare.com/d1/reference/migrations/
- D1 Workers binding API: https://developers.cloudflare.com/d1/worker-api/
- `@cloudflare/vitest-pool-workers` setup: https://developers.cloudflare.com/workers/testing/vitest-integration/
- SQLite PRAGMA table_info: https://www.sqlite.org/pragma.html#pragma_table_info
