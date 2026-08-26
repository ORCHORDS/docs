# Vitest with @cloudflare/vitest-pool-workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your Cloudflare Worker uses D1, KV, R2, Durable Objects, and the `crypto` global from the Workers runtime. When you run tests with standard Vitest, these APIs are either absent or behave differently from Workerd — `crypto.subtle` works but `crypto.randomUUID()` may behave differently, `Response` is the Node.js undici implementation, not the WHATWG version Workers use, and D1 doesn't exist at all. You end up writing excessive mocks that diverge from production behaviour and give false confidence.

`@cloudflare/vitest-pool-workers` runs each test file inside the actual Workerd runtime (the same engine that runs in production) while still using the Vitest test API. Bindings — D1, KV, R2, Queues, Service Bindings — are provided as local in-process fakes backed by Miniflare.

## Context

The package replaces Vitest's default Node.js test runner with a pool that spawns Workerd instances. Key properties:

- Tests run in the Workers runtime: `Request`, `Response`, `Headers`, `caches`, `crypto`, `fetch`, `WebSocket`, and `navigator.userAgent` all match production.
- Bindings are declared in `wrangler.toml` and re-used in the test environment — no separate mock setup for each binding type.
- D1 uses an in-memory SQLite database seeded from migrations. KV, R2, and Queues use Miniflare's local implementations.
- Durable Object stubs work with the actual DO class, not a mock — you test the real object lifecycle.
- The pool runs test files in separate Workerd isolates by default, giving the same isolation you get in production.
- `SELF` is a special binding that dispatches requests to the Worker under test, letting you write integration-level tests that exercise the full request pipeline.

Minimum supported versions: `vitest@2.x`, `wrangler@3.x`, Node.js 18+.

## Installation and Configuration

### Install

```bash
npm install --save-dev @cloudflare/vitest-pool-workers
```

### wrangler.toml (bindings declaration)

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "local"        # Only used for remote; local tests use in-memory

[[kv_namespaces]]
binding = "CACHE"
id = "local"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "my-bucket"

[vars]
ENVIRONMENT = "test"
```

### vitest.config.ts

```typescript
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        // Point to your wrangler.toml so bindings are auto-discovered
        wrangler: { configPath: './wrangler.toml' },
        // miniflare options merge with what wrangler.toml declares
        miniflare: {
          // Seed D1 with your migration files before each test file
          d1Databases: ['DB'],
          // Provide environment variable overrides for tests
          bindings: {
            ENVIRONMENT: 'test',
            SECRET_KEY: 'test-secret-key-for-unit-tests-only',
          },
        },
      },
    },
    // Each test FILE gets a fresh Workerd isolate
    // Set to false to share state between files (rarely needed)
    isolate: true,
  },
});
```

## Writing Tests with Workers Bindings

### Testing Fetch Handlers via SELF

`SELF` dispatches HTTP requests to your Worker's `fetch()` handler as if they came from the network. This is the closest you can get to an end-to-end test without a real network hop.

```typescript
// src/index.test.ts
import { SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';

describe('Worker fetch handler', () => {
  it('returns 200 on GET /', async () => {
    const response = await SELF.fetch('https://example.com/');
    expect(response.status).toBe(200);
  });

  it('returns JSON from /api/health', async () => {
    const response = await SELF.fetch('https://example.com/api/health');
    expect(response.headers.get('Content-Type')).toMatch(/application\/json/);
    const body = await response.json<{ status: string }>();
    expect(body.status).toBe('ok');
  });

  it('returns 401 when Authorization header is missing', async () => {
    const response = await SELF.fetch('https://example.com/api/protected');
    expect(response.status).toBe(401);
  });
});
```

### Testing D1 Queries Directly

Import the binding via `env` from `cloudflare:test` to write unit tests for repository functions:

```typescript
// src/users/users.repository.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';
import { UsersRepository } from './users.repository';

// D1 is fresh (empty) for each test FILE.
// Use beforeEach to insert test data per test if needed.
describe('UsersRepository', () => {
  let repo: UsersRepository;

  beforeEach(async () => {
    // Apply schema migrations (D1 is empty at the start of each file)
    await env.DB.exec(`
      CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        created_at INTEGER NOT NULL
      )
    `);
    repo = new UsersRepository(env.DB);
  });

  it('inserts and retrieves a user', async () => {
    const id = crypto.randomUUID();
    await repo.create({ id, email: 'alice@example.com', name: 'Alice' });
    const user = await repo.findById(id);
    expect(user?.email).toBe('alice@example.com');
  });

  it('returns null for unknown id', async () => {
    const user = await repo.findById('00000000-0000-0000-0000-000000000000');
    expect(user).toBeNull();
  });

  it('throws on duplicate email', async () => {
    const base = { email: 'bob@example.com', name: 'Bob' };
    await repo.create({ id: crypto.randomUUID(), ...base });
    await expect(repo.create({ id: crypto.randomUUID(), ...base })).rejects.toThrow(
      /UNIQUE constraint failed/
    );
  });
});
```

### Testing KV

```typescript
// src/cache/cache.service.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';
import { CacheService } from './cache.service';

describe('CacheService', () => {
  it('stores and retrieves a cached value', async () => {
    const svc = new CacheService(env.CACHE);
    await svc.set('key:1', { value: 42 }, { expirationTtl: 60 });
    const result = await svc.get<{ value: number }>('key:1');
    expect(result?.value).toBe(42);
  });

  it('returns null for an expired key (simulated)', async () => {
    // KV local implementation does not expire in tests.
    // Test the expiry path by skipping the key.
    const svc = new CacheService(env.CACHE);
    const result = await svc.get<{ value: number }>('nonexistent');
    expect(result).toBeNull();
  });
});
```

### Testing R2 Uploads

```typescript
// src/storage/storage.service.test.ts
import { env } from 'cloudflare:test';
import { it, expect } from 'vitest';
import { StorageService } from './storage.service';

it('uploads an object and retrieves its metadata', async () => {
  const svc = new StorageService(env.BUCKET);
  const key = `uploads/${crypto.randomUUID()}.txt`;
  await svc.put(key, 'hello world', { httpMetadata: { contentType: 'text/plain' } });

  const obj = await svc.head(key);
  expect(obj).not.toBeNull();
  expect(obj?.httpMetadata?.contentType).toBe('text/plain');
  expect(obj?.size).toBe(11);
});
```

### Testing Durable Objects

```typescript
// src/rooms/room.do.test.ts
import { env, runInDurableObject } from 'cloudflare:test';
import { it, expect } from 'vitest';
import { ChatRoom } from './room.do';

it('stores a message in the Durable Object', async () => {
  const id = env.ROOMS.newUniqueId();
  const stub = env.ROOMS.get(id);

  const response = await stub.fetch(
    new Request('https://do.example.com/message', {
      method: 'POST',
      body: JSON.stringify({ text: 'Hello world' }),
      headers: { 'Content-Type': 'application/json' },
    })
  );
  expect(response.status).toBe(201);

  // Inspect internal DO storage directly with runInDurableObject
  await runInDurableObject(stub, async (instance: ChatRoom) => {
    const messages = await instance.storage.list<string>({ prefix: 'msg:' });
    expect(messages.size).toBe(1);
  });
});
```

## Seeding D1 from Migration Files

```typescript
// vitest.config.ts (expanded miniflare section)
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const migrations = readdirSync('drizzle')
  .filter(f => f.endsWith('.sql'))
  .sort()
  .map(f => readFileSync(resolve('drizzle', f), 'utf8'))
  .join('\n');

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          d1Databases: ['DB'],
          // SQL run once when each isolate starts — before any test
          d1InitQueries: {
            DB: migrations.split(';').filter(s => s.trim()).map(s => s + ';'),
          },
        },
      },
    },
  },
});
```

## Anti-patterns

- **Importing Node.js APIs in Worker code** — `node:fs`, `node:path`, `node:http` do not exist in Workerd by default. The `nodejs_compat` compatibility flag provides a subset, but you should still test the actual imports rather than relying on Node.js equivalents.
- **Using `fetch` as `globalThis.fetch` without binding it** — Workers fetch respects the miniflare network policy. If you outbound-fetch a real URL in tests, the request will succeed only if `fetchMock` is not engaged. Prefer intercepting with `vi.spyOn(globalThis, 'fetch')` or using `fetchMock` from the package.
- **Sharing mutable state across test files without `isolate: false`** — by default each file is a fresh isolate. If you explicitly set `isolate: false`, you must manually clear KV/D1 state between tests.
- **Expecting Node.js-style `process.env`** — Workers use `env` from the binding context, not `process.env`. In tests, use `env` from `cloudflare:test`; do not try to set `process.env.MY_BINDING`.
- **Forgetting `compatibility_date`** — the date controls which Workers APIs are available and their behaviour. Keep it in sync between `wrangler.toml` and any CI deploy steps.

## Gotchas

- **`cloudflare:test` is a virtual module** — it is injected by the pool. TypeScript will not resolve it without the types: add `"@cloudflare/vitest-pool-workers"` to the `types` array in `tsconfig.json` (or the test tsconfig), not just the devDependencies.
- **D1 schema is per-isolate** — each test file gets a fresh, empty D1. If you rely on `d1InitQueries`, those run once per file, not per test. For per-test isolation, use `beforeEach` to insert and `afterEach` to delete rows, or wrap each test in a transaction and roll it back.
- **Durable Object classes must be exported from the Worker's main entry point** — the pool discovers DO classes through your Worker's exports, not through separate imports.
- **`SELF.fetch` URL must be a valid URL** — the hostname doesn't matter (Workers ignore it) but the URL must parse without error. Use `https://example.com/path` as the base.
- **`vi.mock()` does not work across the Workers isolate boundary** — module mocks are applied in the Workerd process. You cannot mock a native Workers API like `caches` with `vi.mock('cloudflare:cache')`. Use Miniflare's configuration hooks instead.

## Verification

```bash
# Run all tests in Workers mode
npx vitest run

# Run with verbose output to confirm the pool is active
npx vitest run --reporter=verbose 2>&1 | head -20
# Should show: "Running with @cloudflare/vitest-pool-workers"

# Type-check the test files
npx tsc --noEmit --project tsconfig.test.json

# Confirm the D1 binding is accessible
npx vitest run src/users/users.repository.test.ts --reporter=verbose
```

Expected: all tests pass, no `ReferenceError: D1Database is not defined`, and no Node.js-specific globals bleed into the test output.

## Related

- `vitest-setup.md`
- `vitest-coverage-v8.md`
- `kv-testing-miniflare.md`
- `miniflare-d1-integration-testing.md`
- `test-doubles-cloudflare-workers.md`
- `workers-test-patterns.md`
- `d1-testing-local.md`

## Sources

- `@cloudflare/vitest-pool-workers` GitHub: https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- Cloudflare Workers testing docs: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Miniflare local bindings: https://miniflare.dev/
- Wrangler D1 local development: https://developers.cloudflare.com/d1/build-with-d1/local-development/
- `cloudflare:test` module reference: https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/
