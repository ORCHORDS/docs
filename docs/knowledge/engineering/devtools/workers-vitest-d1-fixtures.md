# Vitest Fixtures for D1 Database Testing

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker uses a D1 database and you want deterministic, isolated unit/integration tests: each test should start with a clean schema, optionally pre-seeded with known data, and any mutations made during the test must not bleed into other tests — even when tests run in parallel. You also want to test that your D1 migration SQL files themselves apply cleanly.

---

## Context

`@cloudflare/vitest-pool-workers` provides a Vitest pool that runs tests inside the actual `workerd` runtime, giving access to real D1 bindings (via `getMiniflareD1Database` or the `env` fixture). Each worker context is isolated per test file. For intra-file isolation, D1 does not support savepoints/transactions that can be rolled back, so the recommended pattern is to **drop and recreate the schema** in `beforeEach`, or — for performance — use a per-test in-memory D1 instance.

Key helpers:
- `env.DB` — the D1 binding exposed to the worker under test.
- `applyD1Migrations(db, migrationsDir)` — applies every `.sql` file in a directory in lexicographic order.
- Seeding via `db.batch([...prepare(...).bind(...)])` — executes multiple statements atomically.

---

## Solution

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        // Ensure each test file gets its own miniflare instance
        isolatedStorage: true,
      },
    },
  },
});
```

```sql
-- migrations/0001_create_users.sql
CREATE TABLE IF NOT EXISTS users (
  id          TEXT PRIMARY KEY,
  email       TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  role        TEXT NOT NULL DEFAULT 'user',
  created_at  TEXT NOT NULL
);

CREATE INDEX idx_users_email ON users (email);
```

```sql
-- migrations/0002_create_posts.sql
CREATE TABLE IF NOT EXISTS posts (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,
  published   INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL
);

CREATE INDEX idx_posts_user_id ON posts (user_id);
```

```typescript
// test/fixtures/d1.ts — reusable D1 fixture factory
import {
  env,
  SELF,
  applyD1Migrations,
} from 'cloudflare:test';
import type { D1Database } from '@cloudflare/workers-types';

export interface UserSeed {
  id: string;
  email: string;
  name: string;
  role?: 'user' | 'admin';
}

export interface PostSeed {
  id: string;
  userId: string;
  title: string;
  body: string;
  published?: boolean;
}

/**
 * Apply all D1 migrations and seed optional test data.
 * Call inside `beforeEach` for full isolation per test.
 */
export async function setupD1(
  db: D1Database,
  seeds: { users?: UserSeed[]; posts?: PostSeed[] } = {},
): Promise<void> {
  // Drop all tables so migration SQL runs cleanly
  await db.exec(`
    DROP TABLE IF EXISTS posts;
    DROP TABLE IF EXISTS users;
  `);

  // Re-apply migrations from source SQL files
  await applyD1Migrations(db, './migrations');

  // Seed users
  if (seeds.users?.length) {
    const now = new Date().toISOString();
    const stmts = seeds.users.map((u) =>
      db
        .prepare(
          'INSERT INTO users (id, email, name, role, created_at) VALUES (?, ?, ?, ?, ?)',
        )
        .bind(u.id, u.email, u.name, u.role ?? 'user', now),
    );
    await db.batch(stmts);
  }

  // Seed posts
  if (seeds.posts?.length) {
    const now = new Date().toISOString();
    const stmts = seeds.posts.map((p) =>
      db
        .prepare(
          'INSERT INTO posts (id, user_id, title, body, published, created_at) VALUES (?, ?, ?, ?, ?, ?)',
        )
        .bind(p.id, p.userId, p.title, p.body, p.published ? 1 : 0, now),
    );
    await db.batch(stmts);
  }
}

/** Seed fixtures bundled from JSON files for large datasets. */
export async function seedFromJson(
  db: D1Database,
  fixture: { users?: UserSeed[]; posts?: PostSeed[] },
): Promise<void> {
  return setupD1(db, fixture);
}
```

```typescript
// test/fixtures/seed-data.json
// (import with JSON import assertion — TS 5.3+)
```

```typescript
// test/user.test.ts — per-test isolation with seeded data
import { describe, it, expect, beforeEach } from 'vitest';
import { env, SELF } from 'cloudflare:test';
import { setupD1 } from './fixtures/d1';

describe('User API', () => {
  beforeEach(async () => {
    await setupD1(env.DB, {
      users: [
        { id: 'u1', email: 'alice@example.com', name: 'Alice', role: 'admin' },
        { id: 'u2', email: 'bob@example.com', name: 'Bob' },
      ],
    });
  });

  it('returns 200 with user data for existing user', async () => {
    const res = await SELF.fetch('http://localhost/users/u1');
    expect(res.status).toBe(200);
    const body = await res.json<{ id: string; name: string }>();
    expect(body.id).toBe('u1');
    expect(body.name).toBe('Alice');
  });

  it('returns 404 for unknown user', async () => {
    const res = await SELF.fetch('http://localhost/users/nonexistent');
    expect(res.status).toBe(404);
  });

  it('creates a new user via POST', async () => {
    const res = await SELF.fetch('http://localhost/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: 'u3', email: 'carol@example.com', name: 'Carol' }),
    });
    expect(res.status).toBe(201);

    // Verify persisted — reuse env.DB directly for assertion
    const row = await env.DB
      .prepare('SELECT id, email FROM users WHERE id = ?')
      .bind('u3')
      .first<{ id: string; email: string }>();
    expect(row?.email).toBe('carol@example.com');
  });

  it('rejects duplicate email with 409', async () => {
    const res = await SELF.fetch('http://localhost/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: 'u4', email: 'alice@example.com', name: 'Alice2' }),
    });
    expect(res.status).toBe(409);
  });
});
```

```typescript
// test/migrations.test.ts — test migration files themselves
import { describe, it, expect, beforeEach } from 'vitest';
import { env, applyD1Migrations } from 'cloudflare:test';

describe('D1 Migrations', () => {
  beforeEach(async () => {
    // Reset to empty state
    await env.DB.exec('DROP TABLE IF EXISTS posts; DROP TABLE IF EXISTS users;');
  });

  it('applies all migrations without error', async () => {
    await expect(applyD1Migrations(env.DB, './migrations')).resolves.toBeUndefined();
  });

  it('creates the users table with correct columns', async () => {
    await applyD1Migrations(env.DB, './migrations');
    const info = await env.DB
      .prepare("SELECT name FROM pragma_table_info('users')")
      .all<{ name: string }>();
    const cols = info.results.map((r) => r.name);
    expect(cols).toContain('id');
    expect(cols).toContain('email');
    expect(cols).toContain('role');
    expect(cols).toContain('created_at');
  });

  it('migrations are idempotent (IF NOT EXISTS guards)', async () => {
    await applyD1Migrations(env.DB, './migrations');
    // Applying again must not throw
    await expect(applyD1Migrations(env.DB, './migrations')).resolves.toBeUndefined();
  });

  it('foreign key constraint is enforced on posts -> users', async () => {
    await applyD1Migrations(env.DB, './migrations');
    await expect(
      env.DB
        .prepare(
          'INSERT INTO posts (id, user_id, title, body, created_at) VALUES (?, ?, ?, ?, ?)',
        )
        .bind('p1', 'nonexistent-user', 'Test', 'Body', new Date().toISOString())
        .run(),
    ).rejects.toThrow();
  });
});
```

```typescript
// test/fixture-factory.ts — typed D1 fixture factory for reuse across test suites
import type { D1Database } from '@cloudflare/workers-types';
import { setupD1 } from './fixtures/d1';
import type { UserSeed, PostSeed } from './fixtures/d1';

type FixtureBuilder = {
  withUsers(users: UserSeed[]): FixtureBuilder;
  withPosts(posts: PostSeed[]): FixtureBuilder;
  apply(db: D1Database): Promise<void>;
};

export function d1Fixture(): FixtureBuilder {
  let users: UserSeed[] = [];
  let posts: PostSeed[] = [];

  const builder: FixtureBuilder = {
    withUsers(u) {
      users = u;
      return builder;
    },
    withPosts(p) {
      posts = p;
      return builder;
    },
    apply(db) {
      return setupD1(db, { users, posts });
    },
  };

  return builder;
}

// Usage in a test:
// const fixture = d1Fixture().withUsers([...]).withPosts([...]);
// beforeEach(() => fixture.apply(env.DB));
```

---

## Implementation Details

- **`applyD1Migrations`** is exported by `cloudflare:test` (from `@cloudflare/vitest-pool-workers`). It reads `.sql` files from the given directory and executes them in alphabetical order. File naming convention `0001_`, `0002_` ensures deterministic ordering.
- **`isolatedStorage: true`** in `vitest.config.ts` ensures that D1, KV, and R2 state is reset between test *files*. For intra-file isolation, the `DROP TABLE / applyD1Migrations` pattern in `beforeEach` is required.
- **`db.batch()`** sends multiple statements as a single HTTP round-trip to D1, which is significantly faster than sequential `await db.prepare().run()` calls during seeding.
- **Direct `env.DB` access in tests** — using the binding directly for assertion queries is valid and avoids coupling test assertions to the HTTP layer.

---

## Anti-patterns

- **Sharing DB state between tests** — mutations in one test will fail the next. Always `DROP + migrate` in `beforeEach`.
- **Hardcoding `created_at` in seeds** — use `new Date().toISOString()` so temporal queries in the Worker work correctly relative to "now".
- **`db.exec()` for multi-statement drops in one string** — D1's `exec()` may or may not support multiple `;`-separated statements in the local miniflare environment. Test with `batch()` of individual `DROP TABLE` statements if `exec` fails.
- **Asserting via HTTP when direct DB access is faster** — use `env.DB` directly for write-verification assertions; reserve HTTP assertions for testing the full request/response contract.

---

## Gotchas

- `applyD1Migrations` requires that the migrations directory exists relative to the *vitest process working directory* (your project root), not relative to the test file.
- Foreign key enforcement in D1 (SQLite) is **off by default**. Run `PRAGMA foreign_keys = ON;` at the start of your migration or in a `beforeEach` hook if you want FK violations to throw.
- `env.DB` in `cloudflare:test` is a local in-memory SQLite instance — it does not reflect the remote D1 database. Do not run `wrangler d1 execute` in test setup; always use the in-process binding.
- `db.batch()` wraps statements in a transaction by default in local miniflare. This is consistent with remote D1 behaviour.

---

## Verification

```bash
# Run the full D1 test suite
npx vitest run test/user.test.ts test/migrations.test.ts --reporter verbose

# Confirm per-test isolation: run tests in random order
npx vitest run --sequence.shuffle

# Coverage
npx vitest run --coverage
```

---

## Related

- `documentation/docs/policies/devtools/vitest-unit-testing.md`
- `documentation/docs/policies/devtools/miniflare-integration-testing.md`
- `documentation/docs/policies/devtools/workers-type-safe-bindings-codegen.md`

---

## Sources

- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/d1/reference/migrations/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
