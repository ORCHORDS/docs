# Miniflare Workers D1 Foreign Key Constraint Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Worker inserts child rows into a D1 table that references a parent table via a foreign key. In
production, inserting a child row with a non-existent `parent_id` throws a D1 constraint error. In
your Vitest tests using Miniflare's local D1, the same insert silently succeeds because SQLite
foreign key enforcement is disabled by default (`PRAGMA foreign_keys = OFF`). You need tests that
catch referential integrity violations before they reach production.

## Context

D1 is built on SQLite. SQLite disables foreign key enforcement unless each connection runs
`PRAGMA foreign_keys = ON`. Cloudflare's production D1 runtime enables this pragma. Miniflare uses
`better-sqlite3` under the hood and does not enable the pragma automatically, causing a divergence
between local and production behavior. Tests must explicitly enable foreign keys or use a setup SQL
script that activates the pragma before migration runs.

## 1. Migration SQL with foreign key declarations

```sql
-- migrations/0001_initial.sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id   TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
  id      TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title   TEXT NOT NULL,
  body    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
  id      TEXT PRIMARY KEY,
  post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  body    TEXT NOT NULL
);
```

## 2. Vitest pool config with migration and pragma setup

```ts
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          d1Databases: ['DB'],
        },
      },
    },
    setupFiles: ['./test/setup/d1-fk.ts'],
  },
});
```

```ts
// test/setup/d1-fk.ts
// Emitted before each test file; applies migrations and enables FK enforcement.
import { env } from 'cloudflare:test';
import { readFileSync } from 'node:fs';

const migration = readFileSync('./migrations/0001_initial.sql', 'utf-8');

beforeAll(async () => {
  // Run migration (includes PRAGMA foreign_keys = ON)
  await (env as any).DB.exec(migration);
});

afterEach(async () => {
  // Truncate data but keep schema between tests
  await (env as any).DB.exec(
    'DELETE FROM comments; DELETE FROM posts; DELETE FROM users;',
  );
});
```

## 3. Testing foreign key violation on insert

```ts
// test/db/foreign-keys.test.ts
import { describe, it, expect } from 'vitest';
import { env } from 'cloudflare:test';

interface Env { DB: D1Database }
const db = () => (env as unknown as Env).DB;

describe('D1 foreign key constraints', () => {
  it('rejects a post insert when user_id does not exist', async () => {
    await expect(
      db()
        .prepare(
          'INSERT INTO posts (id, user_id, title, body) VALUES (?1, ?2, ?3, ?4)',
        )
        .bind('post-1', 'nonexistent-user', 'Title', 'Body')
        .run(),
    ).rejects.toThrow(/FOREIGN KEY constraint failed/i);
  });

  it('allows a post insert when the parent user exists', async () => {
    await db()
      .prepare('INSERT INTO users (id, name) VALUES (?1, ?2)')
      .bind('user-1', 'Alice')
      .run();

    const result = await db()
      .prepare(
        'INSERT INTO posts (id, user_id, title, body) VALUES (?1, ?2, ?3, ?4)',
      )
      .bind('post-1', 'user-1', 'Hello', 'World')
      .run();

    expect(result.success).toBe(true);
  });
});
```

## 4. Testing ON DELETE CASCADE behavior

```ts
// test/db/cascade-delete.test.ts
import { describe, it, expect } from 'vitest';
import { env } from 'cloudflare:test';

interface Env { DB: D1Database }
const db = () => (env as unknown as Env).DB;

describe('ON DELETE CASCADE', () => {
  it('deletes child posts when parent user is deleted', async () => {
    // Seed
    await db().exec(`
      INSERT INTO users (id, name) VALUES ('u1', 'Bob');
      INSERT INTO posts (id, user_id, title, body) VALUES ('p1', 'u1', 'T', 'B');
      INSERT INTO posts (id, user_id, title, body) VALUES ('p2', 'u1', 'T', 'B');
    `);

    // Delete parent
    await db()
      .prepare('DELETE FROM users WHERE id = ?1')
      .bind('u1')
      .run();

    const { results } = await db()
      .prepare('SELECT id FROM posts WHERE user_id = ?1')
      .bind('u1')
      .all();

    expect(results).toHaveLength(0);
  });

  it('cascades deletion from posts to comments', async () => {
    await db().exec(`
      INSERT INTO users  (id, name)                      VALUES ('u1', 'Carol');
      INSERT INTO posts  (id, user_id, title, body)      VALUES ('p1', 'u1', 'T', 'B');
      INSERT INTO comments (id, post_id, body)           VALUES ('c1', 'p1', 'Nice!');
    `);

    await db().prepare('DELETE FROM posts WHERE id = ?1').bind('p1').run();

    const { results } = await db()
      .prepare('SELECT id FROM comments WHERE post_id = ?1')
      .bind('p1')
      .all();

    expect(results).toHaveLength(0);
  });
});
```

## 5. Batch insert with rollback on FK violation

```ts
// test/db/batch-fk.test.ts
import { describe, it, expect } from 'vitest';
import { env } from 'cloudflare:test';

interface Env { DB: D1Database }
const db = () => (env as unknown as Env).DB;

describe('batch insert with FK check', () => {
  it('rolls back entire batch when one insert violates FK', async () => {
    await db()
      .prepare('INSERT INTO users (id, name) VALUES (?1, ?2)')
      .bind('u1', 'Dave')
      .run();

    // One valid + one invalid post in a batch
    await expect(
      db().batch([
        db()
          .prepare(
            'INSERT INTO posts (id, user_id, title, body) VALUES (?1, ?2, ?3, ?4)',
          )
          .bind('p1', 'u1', 'Valid', 'ok'),
        db()
          .prepare(
            'INSERT INTO posts (id, user_id, title, body) VALUES (?1, ?2, ?3, ?4)',
          )
          .bind('p2', 'MISSING', 'Invalid', 'fk break'),
      ]),
    ).rejects.toThrow(/FOREIGN KEY constraint failed/i);

    // Rollback: p1 must NOT exist
    const row = await db()
      .prepare('SELECT id FROM posts WHERE id = ?1')
      .bind('p1')
      .first();

    expect(row).toBeNull();
  });
});
```

## Anti-patterns

- **Omitting `PRAGMA foreign_keys = ON` from the migration or setup file**: Miniflare's D1 binding
  uses SQLite with FK enforcement off by default; violations are silently ignored.
- **Resetting the DB with `DROP TABLE` then recreating**: loses the pragma state set earlier in the
  connection; truncate with `DELETE FROM` instead and keep the session open.
- **Asserting only on `result.success`**: a successful `run()` returns `{ success: true }` even
  when constraints would fail if enforcement were on; assert on rejection, not success flag.
- **Using `db.exec()` for multi-statement scripts that mix DML with pragma**: `exec()` runs all
  statements but does not return per-statement results; verify pragma took effect with a separate
  `PRAGMA foreign_keys;` query in tests.

## Gotchas

- The `PRAGMA foreign_keys = ON` must run on the **same connection** as the subsequent DML. In
  Miniflare, `better-sqlite3` uses a single persistent connection per D1 binding instance; running
  the pragma in `beforeAll` is sufficient for all statements in the same test file.
- D1's production runtime implicitly enables FK enforcement; your Worker code does not need to run
  the pragma itself. Tests must replicate this behavior explicitly because Miniflare does not.
- `db.batch()` wraps its statements in an implicit transaction. A FK violation in any statement
  causes the entire batch to roll back; test this behavior to confirm your error handler surfaces
  the correct message.
- `ON DELETE SET NULL` requires the FK column to be nullable. If you declare `user_id TEXT NOT NULL`
  and use `ON DELETE SET NULL`, the migration will fail silently in SQLite or throw a constraint
  error depending on the version. Test cascade behavior explicitly.

## Verification

```bash
# Run FK constraint tests
npx vitest run test/db/foreign-keys.test.ts test/db/cascade-delete.test.ts

# Confirm PRAGMA is active (should print "1")
npx wrangler d1 execute my-db --local --command "PRAGMA foreign_keys;"

# Run all D1 tests in watch mode
npx vitest --reporter=verbose test/db/
```

## Related

- `miniflare-d1-integration-testing.md`
- `miniflare-d1-migration-testing.md`
- `d1-batch-transactions-vitest.md`
- `vitest-d1-prepared-statement-caching-testing.md`
- `contract-testing-workers-d1-schema-validation.md`

## Sources

- https://developers.cloudflare.com/d1/sql-api/foreign-keys/
- https://www.sqlite.org/foreignkeys.html
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare
