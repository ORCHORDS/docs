# miniflare-d1-integration-testing

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Integration tests that exercise D1 queries either hit the
real Cloudflare network (slow, needs credentials, costs
reads) or skip D1 entirely and mock at the wrong layer.
Transaction rollbacks and batch operations are untested
locally, so regressions reach staging undetected.

## Context

Cloudflare's `@cloudflare/vitest-pool-workers` package runs
Vitest tests inside a real `workerd` runtime, giving you a
local D1 binding backed by SQLite with the same semantics
as production. Miniflare v3 (the underlying engine) also
exposes a standalone API for test environments that do not
use Vitest. Together these cover seeding, rollbacks, batch
operations, and mobile vs. desktop request simulation
without any network calls or Cloudflare account access.

## Environment Setup

Install once:

```bash
npm install --save-dev vitest \
  @cloudflare/vitest-pool-workers \
  wrangler
```

`vitest.config.ts` pool configuration:

```ts
import { defineConfig } from 'vitest/config';
import {
  defineWorkersConfig,
} from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

`wrangler.toml` excerpt:

```toml
[[d1_databases]]
binding     = "DB"
database_name = "example project-dev"
database_id   = "local"          # any string for local runs
migrations_dir = "migrations"
```

The pool starts `workerd` once per worker, runs all test
files inside it, and tears it down afterwards. Each test
file gets an isolated in-memory SQLite instance by default.

## Seeding Test Data

Apply schema and seed inside `beforeEach` so every test
starts from a clean, known state:

```ts
// tests/db.setup.ts
import {
  env,
  createExecutionContext,
} from 'cloudflare:test';

export async function seedDb() {
  const { DB } = env<{ DB: D1Database }>();

  // Apply migrations
  await DB.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id   TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'user'
    );
    CREATE TABLE IF NOT EXISTS sessions (
      token   TEXT PRIMARY KEY,
      user_id TEXT REFERENCES users(id)
    );
  `);

  // Seed canonical rows
  await DB.prepare(
    'INSERT INTO users (id, name, role) VALUES (?, ?, ?)'
  )
    .bind('u1', 'Alice', 'admin')
    .run();

  await DB.prepare(
    'INSERT INTO users (id, name, role) VALUES (?, ?, ?)'
  )
    .bind('u2', 'Bob', 'user')
    .run();
}
```

```ts
// tests/users.test.ts
import { env }     from 'cloudflare:test';
import { seedDb }  from './db.setup';
import { describe, it, expect, beforeEach } from 'vitest';

describe('user queries', () => {
  beforeEach(async () => {
    const { DB } = env<{ DB: D1Database }>();
    await DB.exec('DELETE FROM sessions; DELETE FROM users;');
    await seedDb();
  });

  it('returns admin users', async () => {
    const { DB } = env<{ DB: D1Database }>();
    const result = await DB.prepare(
      'SELECT * FROM users WHERE role = ?'
    )
      .bind('admin')
      .all<{ id: string; name: string }>();

    expect(result.results).toHaveLength(1);
    expect(result.results[0].name).toBe('Alice');
  });
});
```

`DB.exec()` accepts multi-statement SQL separated by `;`.
Use it for teardown; use `prepare().bind().run()` for seeding
so parameter types are enforced by the D1 binding layer.

## Batch Operations

D1 `batch()` executes multiple statements in a single HTTP
round-trip in production. Test it the same way:

```ts
it('batch-inserts products atomically', async () => {
  const { DB } = env<{ DB: D1Database }>();

  const stmts = [
    DB.prepare(
      'INSERT INTO products (id, name, price_pence) VALUES (?, ?, ?)'
    ).bind('p1', 'Widget', 199),
    DB.prepare(
      'INSERT INTO products (id, name, price_pence) VALUES (?, ?, ?)'
    ).bind('p2', 'Gadget', 499),
  ];

  const results = await DB.batch(stmts);
  expect(results).toHaveLength(2);
  expect(results[0].success).toBe(true);
  expect(results[1].success).toBe(true);

  const count = await DB.prepare(
    'SELECT COUNT(*) as c FROM products'
  ).first<{ c: number }>();
  expect(count?.c).toBe(2);
});
```

Batch error behaviour:

| Scenario                        | Outcome                     |
|---------------------------------|-----------------------------|
| All statements succeed          | Array of success results    |
| One statement fails (UNIQUE)    | Entire batch rolls back     |
| Malformed SQL in any statement  | Throws before execution     |
| Empty array passed to batch()   | Returns empty array         |

## Transaction Rollback Testing

D1 supports `BEGIN`/`COMMIT`/`ROLLBACK` via `exec()`.
Test rollback paths explicitly:

```ts
it('rolls back on constraint violation', async () => {
  const { DB } = env<{ DB: D1Database }>();

  // Seed a conflicting row first
  await DB.prepare(
    'INSERT INTO users (id, name, role) VALUES (?, ?, ?)'
  )
    .bind('dup', 'Duplicate', 'user')
    .run();

  // This batch should fail: second row duplicates PK
  const conflict = DB.batch([
    DB.prepare(
      'INSERT INTO users (id, name, role) VALUES (?, ?, ?)'
    ).bind('new1', 'Carol', 'user'),
    DB.prepare(
      'INSERT INTO users (id, name, role) VALUES (?, ?, ?)'
    ).bind('dup', 'Oops', 'user'),  // duplicate PK
  ]);

  await expect(conflict).rejects.toThrow();

  // Confirm 'new1' was NOT inserted (batch rolled back)
  const ghost = await DB.prepare(
    'SELECT id FROM users WHERE id = ?'
  )
    .bind('new1')
    .first();
  expect(ghost).toBeNull();
});
```

## Mobile vs. Desktop Request Simulation

Test Worker request-handling branches (user-agent parsing,
viewport hints, CF-Device-Type) without leaving the local
runtime:

```ts
import { createRequest } from 'cloudflare:test';

function makeRequest(
  path: string,
  ua: string,
  cfDeviceType: string
) {
  return new Request(`https://example.com${path}`, {
    headers: {
      'User-Agent':    ua,
      'CF-Device-Type': cfDeviceType,
    },
  });
}

const MOBILE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) ' +
  'AppleWebKit/605.1.15 (KHTML, like Gecko) ' +
  'Version/17.0 Mobile/15E148 Safari/604.1';

const DESKTOP_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) ' +
  'AppleWebKit/537.36 (KHTML, like Gecko) ' +
  'Chrome/126.0.0.0 Safari/537.36';

it('serves compact JSON for mobile callers', async () => {
  const req = makeRequest('/api/feed', MOBILE_UA, 'mobile');
  const res = await worker.fetch(req, env);
  const body = await res.json<{ compact: boolean }>();
  expect(body.compact).toBe(true);
});

it('serves full JSON for desktop callers', async () => {
  const req = makeRequest('/api/feed', DESKTOP_UA, 'desktop');
  const res = await worker.fetch(req, env);
  const body = await res.json<{ compact: boolean }>();
  expect(body.compact).toBe(false);
});
```

Common CF header values to simulate:

| Header             | Mobile value | Desktop value |
|--------------------|--------------|---------------|
| `CF-Device-Type`   | `mobile`     | `desktop`     |
| `CF-IPCountry`     | `US`         | `US`          |
| `Accept`           | `*/*`        | `text/html,…` |

## Anti-patterns

- Calling `wrangler d1 execute` in test setup — it hits the
  network and requires a valid `database_id` in Cloudflare.
- Using `jest.mock()` to stub the D1 binding — the mock
  never exercises SQLite constraints or batch rollback
  semantics.
- Sharing one `DB` instance across parallel test files
  without isolation — concurrent writes corrupt state.
- Testing only happy-path `prepare().bind().run()` and
  skipping `batch()` — production code uses batch and the
  rollback contract is different.
- Forgetting to tear down between tests — a passing test
  that leaves stale rows causes false failures in later
  tests when count assertions are used.

## Gotchas

- `workerd` binary must be present; it is installed by
  `wrangler` as a transitive dependency. Confirm with
  `npx wrangler --version`.
- `env` imported from `'cloudflare:test'` is only available
  inside test files executed by the pool — regular Node.js
  `import` in non-test files throws `MODULE_NOT_FOUND`.
- `DB.exec()` does not return typed results; use
  `DB.prepare().all()` for assertions that check row data.
- D1 local mode uses WAL journal; concurrent writes that
  would deadlock in production may succeed in tests because
  SQLite WAL is more permissive — do not conclude there is
  no contention.
- The `migrations_dir` in `wrangler.toml` is NOT
  automatically applied in test runs; you must call
  `DB.exec(migrationSql)` or `DB.batch([...])` yourself in
  `beforeAll`.

## Verification

```bash
# Run D1 integration tests only
npx vitest run --reporter=verbose tests/db/

# Show workerd version being used
npx wrangler --version

# Confirm pool workers configuration resolves
npx vitest --pool=workers --reporter=list \
  tests/db/users.test.ts
```

All tests should complete without network calls. Set
`CI=true` to suppress watch mode.

## Related

- `testing/d1-testing-local.md`
- `testing/kv-testing-miniflare.md`
- `testing/workers-unit-testing-fetch-mocking.md`
- `testing/test-doubles-cloudflare-workers.md`
- `testing/transactional-test-rollback.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/d1/reference/local-development/
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://miniflare.dev/
- https://vitest.dev/config/#pool
