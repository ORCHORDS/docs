# D1 Database Fixtures and Test Isolation with Vitest + Miniflare

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Unit and integration tests for Cloudflare Workers that read or write D1 databases fail intermittently because each test run shares mutable state. Developers see tests passing in isolation but failing in the full suite, or find that seed data from one test corrupts assertions in another. There is no out-of-the-box test-fixture or rollback mechanism in Miniflare 3 / `@cloudflare/vitest-pool-workers`.

---

## Context

`@cloudflare/vitest-pool-workers` runs every test file inside a real Miniflare v3 isolate. Each isolate gets its own in-memory D1 instance, but **tests within the same file share that instance** unless you explicitly reset it between tests. Because D1 is transactional and supports pragmas, you can layer schema migrations, fixture factories, and snapshot helpers on top of the raw binding to achieve full per-test isolation without hitting a deployed database.

Stack:
- `vitest` ^2.x
- `@cloudflare/vitest-pool-workers` ^0.5.x
- `wrangler` ^3.x (for `wrangler.toml` schema)
- TypeScript 5.x

---

## Solution

### 1. `wrangler.toml` — declare a local D1 binding

```toml
[[d1_databases]]
binding = "DB"
database_name = "app"
database_id = "local-test-db"
```

### 2. `vitest.config.ts` — pool workers config

```typescript
import { defineConfig } from 'vitest/config';
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          // Each test file gets its own isolate with a fresh in-memory D1.
          isolatedStorage: true,
        },
      },
    },
  },
});
```

### 3. Schema migration helper

```typescript
// test/helpers/migrations.ts
import type { D1Database } from '@cloudflare/workers-types';

const SCHEMA_SQL = /* sql */ `
  CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT    NOT NULL UNIQUE,
    name       TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS orders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_cents INTEGER NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'pending'
  );
`;

/** Run the full schema against an in-memory D1 instance. */
export async function runMigrations(db: D1Database): Promise<void> {
  const statements = SCHEMA_SQL
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => db.prepare(s));

  await db.batch(statements);
}

/** Drop all tables to reset state between tests. */
export async function teardownSchema(db: D1Database): Promise<void> {
  const { results } = await db
    .prepare(`SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'`)
    .all<{ name: string }>();

  const drops = results.map((r) => db.prepare(`DROP TABLE IF EXISTS ${r.name}`));
  if (drops.length) await db.batch(drops);
}
```

### 4. Fixture factory

```typescript
// test/helpers/fixtures.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface UserFixture {
  id: number;
  email: string;
  name: string;
}

export interface OrderFixture {
  id: number;
  userId: number;
  totalCents: number;
  status: string;
}

let _userSeq = 0;
let _orderSeq = 0;

/** Reset sequence counters - call in beforeEach. */
export function resetSequences(): void {
  _userSeq = 0;
  _orderSeq = 0;
}

/** Insert a user row with deterministic defaults. */
export async function createUser(
  db: D1Database,
  overrides: Partial<Omit<UserFixture, 'id'>> = {},
): Promise<UserFixture> {
  const seq = ++_userSeq;
  const email = overrides.email ?? `user${seq}@example.com`;
  const name  = overrides.name  ?? `Test User ${seq}`;

  const result = await db
    .prepare('INSERT INTO users (email, name) VALUES (?, ?) RETURNING *')
    .bind(email, name)
    .first<UserFixture>();

  if (!result) throw new Error('Failed to insert user fixture');
  return result;
}

/** Insert an order row linked to a user. */
export async function createOrder(
  db: D1Database,
  userId: number,
  overrides: Partial<Omit<OrderFixture, 'id' | 'userId'>> = {},
): Promise<OrderFixture> {
  ++_orderSeq;
  const totalCents = overrides.totalCents ?? 1000;
  const status     = overrides.status     ?? 'pending';

  const result = await db
    .prepare(
      'INSERT INTO orders (user_id, total_cents, status) VALUES (?, ?, ?) RETURNING *',
    )
    .bind(userId, totalCents, status)
    .first<OrderFixture>();

  if (!result) throw new Error('Failed to insert order fixture');
  return result;
}
```

### 5. Test file with `beforeEach` / `afterEach` isolation

```typescript
// test/orders.test.ts
import { env }                          from 'cloudflare:test';
import { describe, it, expect,
         beforeEach, afterEach }        from 'vitest';
import { runMigrations, teardownSchema } from './helpers/migrations';
import { createUser, createOrder,
         resetSequences }               from './helpers/fixtures';
import { getOrdersByUser }              from '../src/db/queries';

describe('orders queries', () => {
  beforeEach(async () => {
    resetSequences();
    await runMigrations(env.DB);
  });

  afterEach(async () => {
    await teardownSchema(env.DB);
  });

  it('returns all orders for a user', async () => {
    const user  = await createUser(env.DB);
    const order = await createOrder(env.DB, user.id, { totalCents: 2500 });

    const rows = await getOrdersByUser(env.DB, user.id);

    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe(order.id);
    expect(rows[0].total_cents).toBe(2500);
  });

  it('returns empty array when user has no orders', async () => {
    const user = await createUser(env.DB);
    const rows = await getOrdersByUser(env.DB, user.id);
    expect(rows).toHaveLength(0);
  });

  it('does not return orders for a different user', async () => {
    const userA = await createUser(env.DB);
    const userB = await createUser(env.DB);
    await createOrder(env.DB, userA.id);

    const rows = await getOrdersByUser(env.DB, userB.id);
    expect(rows).toHaveLength(0);
  });
});
```

### 6. Transaction rollback pattern (savepoints)

D1 supports SQLite savepoints, enabling lightweight rollback without full schema teardown:

```typescript
// test/helpers/transaction.ts
import type { D1Database } from '@cloudflare/workers-types';

let savepointId = 0;

export async function withRollback(
  db: D1Database,
  fn: () => Promise<void>,
): Promise<void> {
  const sp = `sp_${++savepointId}`;
  await db.prepare(`SAVEPOINT ${sp}`).run();
  try {
    await fn();
  } finally {
    await db.prepare(`ROLLBACK TO SAVEPOINT ${sp}`).run();
    await db.prepare(`RELEASE SAVEPOINT ${sp}`).run();
  }
}
```

Usage in tests:

```typescript
import { withRollback } from './helpers/transaction';

it('rolls back mutations after test', async () => {
  await withRollback(env.DB, async () => {
    const user = await createUser(env.DB);
    // mutations here are reverted after fn() returns
    expect(user.id).toBeGreaterThan(0);
  });

  const { results } = await env.DB.prepare('SELECT * FROM users').all();
  expect(results).toHaveLength(0);
});
```

### 7. Snapshot testing D1 rows

```typescript
// test/snapshot.test.ts
import { env }               from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';
import { runMigrations }    from './helpers/migrations';
import { createUser }       from './helpers/fixtures';

describe('D1 snapshot tests', () => {
  beforeEach(async () => {
    await runMigrations(env.DB);
  });

  it('user row shape matches snapshot', async () => {
    const user = await createUser(env.DB, { email: 'snap@test.com', name: 'Snap User' });

    // Strip auto-generated timestamp for deterministic snapshot.
    const { created_at: _ts, ...rest } = user as any;
    expect(rest).toMatchInlineSnapshot(`
      {
        "email": "snap@test.com",
        "id": 1,
        "name": "Snap User",
      }
    `);
  });
});
```

---

## Implementation Details

- `isolatedStorage: true` in the Miniflare config ensures that each **test file** gets its own D1 namespace. Tests **within** a file still share the same D1 instance, which is why `beforeEach`/`afterEach` teardown is required.
- `db.batch()` executes multiple statements in a single round-trip and within one implicit transaction, making schema migration fast.
- `RETURNING *` on INSERT is supported by D1 (SQLite 3.35+) and avoids a second SELECT for fixture setup.
- Savepoints are cheaper than full schema teardown when only a subset of tables need isolation.
- Sequence counters (`_userSeq`) ensure unique email addresses across tests in the same file without relying on `Math.random()`.

---

## Anti-patterns

- **Shared static seed data**: Inserting seed rows in `beforeAll` and relying on them across tests creates ordering dependencies and makes individual test runs meaningless.
- **Hardcoding row IDs**: `expect(row.id).toBe(1)` will break when tests run in parallel or when other fixtures insert rows first. Capture the returned ID from the INSERT instead.
- **Skipping teardown**: Leaving rows in the DB after a test that creates many rows causes subsequent tests to see unexpected data, especially when testing `COUNT(*)` or pagination.
- **Using the deployed D1 for unit tests**: Always use the in-memory Miniflare D1. Pointing tests at a real deployed database introduces network latency, cost, and state pollution.
- **Running `DROP TABLE` without checking existence**: Always use `IF EXISTS` to prevent teardown from failing on a partially-migrated schema.

---

## Gotchas

- D1's `batch()` does **not** wrap statements in a user-level transaction by default - each statement is atomic individually. Wrap with explicit `BEGIN`/`COMMIT` if you need multi-statement atomicity.
- `SAVEPOINT` rollback via D1 is only reliable when you do not call `db.batch()` across the savepoint boundary, because `batch()` may issue implicit transactions internally.
- `env.DB` is only available within the `@cloudflare/vitest-pool-workers` runner. Standard Node.js Vitest cannot import `cloudflare:test`.
- Schema migrations run in `beforeEach` add ~5-15 ms per test. For large schemas (50+ tables), switch to `beforeAll` + savepoint rollback.
- Vitest inline snapshots are written to the test source file on first run. Commit them alongside test code.

---

## Verification

```bash
# Run the full test suite with verbose output
npx vitest run --reporter=verbose

# Run a single test file
npx vitest run test/orders.test.ts

# Watch mode for TDD
npx vitest watch test/orders.test.ts

# Confirm no shared state by running tests in random order
npx vitest run --sequence.shuffle
```

Expected output: all tests green, no "UNIQUE constraint failed" or "no such table" errors.

---

## Related

- `documentation/docs/policies/testing/workers-contract-testing-pact.md`
- `documentation/docs/policies/testing/workers-mutation-testing-stryker.md`
- `documentation/workers/d1-query-patterns.md`
- `documentation/workers/miniflare-local-dev.md`

---

## Sources

- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/d1/
- https://miniflare.dev/
- https://vitest.dev/guide/snapshot
