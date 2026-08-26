# Vitest D1 Prepared Statement Caching Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Worker prepares D1 statements with `db.prepare(sql)` and reuses them across
requests via a module-scoped cache. In tests you discover that the mock `D1Database` never validates
whether `.prepare()` is called once (cached) or repeatedly (uncached), so you cannot verify your
caching logic. A regression where the cache key is accidentally re-computed on every request goes
undetected until production query latency degrades.

## Context

`D1Database.prepare()` in the Workers runtime returns a `D1PreparedStatement`. Calling it is cheap
locally but each call crosses the SQLite binding boundary in production; caching prepared statements
at module scope reduces per-request overhead for hot paths. Miniflare's D1 implementation binds to
`better-sqlite3` locally, where `.prepare()` is synchronous and fast — masking the cost. Tests must
spy on `.prepare()` call counts to enforce caching contracts independently of the underlying engine.

## 1. Module-scoped prepared statement cache

```ts
// src/db/statements.ts
import type { D1Database } from '@cloudflare/workers-types';

interface StatementCache {
  listItems?: D1PreparedStatement;
  getItem?: D1PreparedStatement;
  insertItem?: D1PreparedStatement;
}

const cache: StatementCache = {};

export function getStatements(db: D1Database) {
  if (!cache.listItems) {
    cache.listItems = db.prepare(
      'SELECT id, name, created_at FROM items ORDER BY created_at DESC LIMIT 50',
    );
  }
  if (!cache.getItem) {
    cache.getItem = db.prepare(
      'SELECT id, name, body FROM items WHERE id = ?1',
    );
  }
  if (!cache.insertItem) {
    cache.insertItem = db.prepare(
      'INSERT INTO items (id, name, body) VALUES (?1, ?2, ?3)',
    );
  }
  return cache as Required<StatementCache>;
}

/** Call between requests in tests to reset module cache. */
export function _resetStatementCache() {
  cache.listItems = undefined;
  cache.getItem = undefined;
  cache.insertItem = undefined;
}
```

## 2. Vitest test environment setup

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
  },
});
```

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "local-test"
```

## 3. Spying on prepare() call counts

```ts
// test/db/statements.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getStatements, _resetStatementCache } from '../../src/db/statements';

function makeD1Mock(): D1Database {
  const stmtMock: D1PreparedStatement = {
    bind: vi.fn().mockReturnThis(),
    first: vi.fn().mockResolvedValue(null),
    all: vi.fn().mockResolvedValue({ results: [], success: true }),
    run: vi.fn().mockResolvedValue({ success: true }),
  } as unknown as D1PreparedStatement;

  return {
    prepare: vi.fn().mockReturnValue(stmtMock),
    exec: vi.fn(),
    batch: vi.fn(),
    dump: vi.fn(),
  } as unknown as D1Database;
}

describe('statement cache', () => {
  let db: D1Database;

  beforeEach(() => {
    _resetStatementCache();
    db = makeD1Mock();
  });

  afterEach(() => {
    _resetStatementCache();
  });

  it('calls prepare() exactly once per statement on first access', () => {
    getStatements(db);
    // Three distinct SQL strings → three prepare calls
    expect(db.prepare).toHaveBeenCalledTimes(3);
  });

  it('does NOT call prepare() again on subsequent calls with the same db', () => {
    getStatements(db);
    getStatements(db);
    getStatements(db);
    // Cache hit: still only 3 total prepare calls
    expect(db.prepare).toHaveBeenCalledTimes(3);
  });

  it('re-prepares statements when the cache is reset', () => {
    getStatements(db);
    _resetStatementCache();
    getStatements(db);
    expect(db.prepare).toHaveBeenCalledTimes(6); // 3 + 3
  });
});
```

## 4. Contract test: prepared SQL strings are stable

```ts
// test/db/sql-contracts.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getStatements, _resetStatementCache } from '../../src/db/statements';

describe('prepared SQL contract', () => {
  beforeEach(() => {
    _resetStatementCache();
  });

  it('listItems SQL matches snapshot', () => {
    const calls: string[] = [];
    const db = {
      prepare: vi.fn((sql: string) => {
        calls.push(sql);
        return { bind: vi.fn().mockReturnThis(), all: vi.fn() };
      }),
    } as unknown as D1Database;

    getStatements(db);

    const listItemsSql = calls[0];
    expect(listItemsSql).toMatchInlineSnapshot(
      `"SELECT id, name, created_at FROM items ORDER BY created_at DESC LIMIT 50"`,
    );
  });
});
```

## 5. Integration test: bind() receives correct positional parameters

```ts
// test/db/bind-params.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getStatements, _resetStatementCache } from '../../src/db/statements';
import { fetchItem } from '../../src/db/queries';

describe('bind parameter contract', () => {
  beforeEach(() => { _resetStatementCache(); });

  it('getItem binds the id as positional ?1', async () => {
    const stmtMock = {
      bind: vi.fn().mockReturnThis(),
      first: vi.fn().mockResolvedValue({ id: '123', name: 'Test', body: '' }),
    } as unknown as D1PreparedStatement;

    const db = {
      prepare: vi.fn().mockReturnValue(stmtMock),
    } as unknown as D1Database;

    await fetchItem(db, '123');

    // bind() must be called with exactly the id string
    expect(stmtMock.bind).toHaveBeenCalledWith('123');
    expect(stmtMock.first).toHaveBeenCalledTimes(1);
  });
});
```

```ts
// src/db/queries.ts
import { getStatements } from './statements';

export async function fetchItem(db: D1Database, id: string) {
  const { getItem } = getStatements(db);
  return getItem.bind(id).first<{ id: string; name: string; body: string }>();
}
```

## 6. Detecting cache pollution across worker instances

```ts
// test/db/cache-isolation.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getStatements, _resetStatementCache } from '../../src/db/statements';

describe('cache does not bleed across simulated instances', () => {
  beforeEach(() => { _resetStatementCache(); });

  it('first db instance populates the cache', () => {
    const db1 = { prepare: vi.fn().mockReturnValue({}) } as unknown as D1Database;
    getStatements(db1);
    expect(db1.prepare).toHaveBeenCalledTimes(3);
  });

  it('second db instance sees an already-warm cache', () => {
    const db1 = { prepare: vi.fn().mockReturnValue({}) } as unknown as D1Database;
    getStatements(db1);

    // A new D1Database object (simulating a new request binding)
    const db2 = { prepare: vi.fn().mockReturnValue({}) } as unknown as D1Database;
    getStatements(db2);

    // db2 should NOT have prepare() called because the cache is already warm
    expect(db2.prepare).not.toHaveBeenCalled();
  });
});
```

## Anti-patterns

- **Never resetting the module-scope cache between tests**: earlier tests warm the cache for later
  tests, making call-count assertions on `prepare()` unreliable.
- **Using `vi.mock` on the entire `statements` module**: replaces the caching logic under test;
  instead spy only on the `D1Database` mock.
- **Asserting only on query results, not on `prepare()` call frequency**: the caching contract is
  invisible to result-only assertions; a regression that calls `prepare()` 100× per request passes.
- **Testing only with Miniflare's real D1 binding**: the real binding auto-caches internally in
  `better-sqlite3`, masking duplicate `prepare()` calls at the JS layer.

## Gotchas

- Module-scope caches in Workers persist across requests within the same isolate but are reset when
  the isolate is evicted. In Vitest, each test file runs in a separate worker, so the cache starts
  empty per file, but tests within the same file share the module scope. Always call
  `_resetStatementCache()` in `beforeEach`.
- `D1PreparedStatement.bind()` is chainable — it returns a new statement with bound params, not
  `this`. Your mock must return a fresh object (or itself) from `bind()` so `.first()` / `.all()`
  can be called on the return value.
- The `?1`, `?2`, `?3` positional syntax is D1-specific (SQLite named params). If you switch to
  named params (`:id`), `.bind()` accepts an object; update both the SQL snapshot and the bind spy
  assertion.
- Prepared statement caches stored at module scope are shared across concurrent request handlers
  within the same isolate. Ensure the cached `D1PreparedStatement` is only used as immutable via
  `.bind(...).first()`; never mutate it between calls.

## Verification

```bash
# Run statement cache tests
npx vitest run test/db/statements.test.ts test/db/sql-contracts.test.ts

# Verify bind parameter contracts
npx vitest run test/db/bind-params.test.ts --reporter=verbose

# Run all D1 tests together
npx vitest run test/db/
```

## Related

- `d1-testing-local.md`
- `miniflare-d1-integration-testing.md`
- `d1-batch-transactions-vitest.md`
- `vitest-cloudflare-pool-workers.md`
- `contract-testing-workers-d1-schema-validation.md`

## Sources

- https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://vitest.dev/guide/mocking.html
- https://developers.cloudflare.com/d1/best-practices/
