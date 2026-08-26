# Testing Cloudflare Workers with Miniflare and Vitest

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your Cloudflare Workers project has grown to the point where manual testing with
`wrangler dev` is insufficient. You are making changes to business logic and only
discovering regressions after deploy to staging. Or you have a shared `packages/`
library consumed by multiple Workers and you need confidence that a change does not
silently break a downstream consumer. Or you simply want CI to give you a signal
before a PR merges.

The challenge: Workers run in a V8 isolate, not Node.js. Standard Jest or Vitest tests
that run in Node.js cannot access Workers bindings (KV, D1, R2, Durable Objects,
environment variables) without a simulation layer. Miniflare is that simulation layer.

---

## Context

**Miniflare** is an open-source local simulator for the Cloudflare Workers runtime. It
implements the Workers runtime APIs (including KV, D1, R2, Queues, Durable Objects)
in Node.js, so tests can exercise the full binding surface without deploying to
Cloudflare.

**Vitest** is a Vite-native test runner that supports ESM natively, runs tests in
parallel, has a watch mode, and integrates cleanly with TypeScript. It is the
recommended test runner for Workers projects in 2026 (the older `jest-environment-
miniflare` package is deprecated in favour of the official `@cloudflare/vitest-pool-
workers`).

**The official integration** as of Wrangler 3.x and Miniflare 3.x is:
- `vitest` as the test runner
- `@cloudflare/vitest-pool-workers` as the Vitest pool that runs tests inside an
  actual Workers runtime (using Workerd, the open-source Workers runtime)
- Tests run in the same isolate as your Worker code, with real Workers APIs

This is not a mock — it is a real Workerd instance running your test. The difference
matters: `fetch()`, `caches`, `crypto.subtle`, and all binding APIs behave exactly as
they do in production.

---

## Section 1 — Project Setup

**Install dependencies:**
```bash
pnpm add -D vitest @cloudflare/vitest-pool-workers wrangler
```

**`vitest.config.ts`:**
```typescript
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

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

This tells Vitest to use `@cloudflare/vitest-pool-workers` as the pool and to read
your Worker's bindings and environment from `wrangler.toml`.

**`wrangler.toml` (test bindings):**
Add a `[env.test]` block to isolate test resources from your development bindings:
```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "MY_KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[env.test]
[[env.test.kv_namespaces]]
binding = "MY_KV"
id = "test-kv-namespace"

[[env.test.d1_databases]]
binding = "DB"
database_name = "my-db-test"
database_id = "test-d1-id"
```

---

## Section 2 — Writing Tests

**Basic Worker test:**
```typescript
import { env, createExecutionContext, waitOnExecutionContext }
  from 'cloudflare:test';
import { describe, it, expect, beforeAll } from 'vitest';
import worker from '../src/index';

describe('Worker', () => {
  it('returns 200 for GET /', async () => {
    const request = new Request('https://example.com/');
    const ctx = createExecutionContext();
    const response = await worker.fetch(request, env, ctx);
    await waitOnExecutionContext(ctx);
    expect(response.status).toBe(200);
  });
});
```

Note: `env` is the real binding environment — `env.MY_KV`, `env.DB`, etc. are real
Miniflare implementations of KV and D1, not mocks.

**Testing KV interactions:**
```typescript
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';
import { getFeatureFlag, setFeatureFlag } from '../src/lib/feature-flags';

describe('feature flags', () => {
  beforeEach(async () => {
    // Clean state before each test — KV is in-memory in tests
    await env.MY_KV.delete('flag:new-checkout');
  });

  it('returns false for an unset flag', async () => {
    const result = await getFeatureFlag(env.MY_KV, 'new-checkout');
    expect(result).toBe(false);
  });

  it('returns true after setting a flag', async () => {
    await setFeatureFlag(env.MY_KV, 'new-checkout', true);
    const result = await getFeatureFlag(env.MY_KV, 'new-checkout');
    expect(result).toBe(true);
  });
});
```

**Testing D1 interactions:**
```typescript
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';
import { createUser, getUserById } from '../src/lib/users';

describe('users', () => {
  beforeEach(async () => {
    // Apply migrations to the test D1 instance
    await env.DB.exec(`
      CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        created_at INTEGER NOT NULL
      )
    `);
    await env.DB.exec('DELETE FROM users');
  });

  it('creates and retrieves a user', async () => {
    const user = await createUser(env.DB, {
      id: 'usr_01',
      email: 'test@example.com',
      created_at: Date.now(),
    });
    const retrieved = await getUserById(env.DB, 'usr_01');
    expect(retrieved?.email).toBe('test@example.com');
  });
});
```

**Testing R2 interactions:**
```typescript
import { env } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';
import { storeUserAvatar, getUserAvatarKey } from '../src/lib/avatars';

describe('avatars', () => {
  it('stores and retrieves an avatar', async () => {
    const data = new Uint8Array([0xFF, 0xD8, 0xFF]); // JPEG magic bytes
    await storeUserAvatar(env.AVATARS, 'usr_01', data);
    const key = getUserAvatarKey('usr_01');
    const obj = await env.AVATARS.get(key);
    expect(obj).not.toBeNull();
  });
});
```

---

## Section 3 — Test Organisation for a pnpm Workspace

In a monorepo, place tests adjacent to the code they test:

```
workers/api/
├── src/
│   ├── index.ts
│   └── lib/
│       ├── users.ts
│       └── users.test.ts   ← Unit test for users.ts
├── test/
│   └── integration/
│       └── routes.test.ts  ← Integration test for HTTP routes
├── wrangler.toml
└── vitest.config.ts

packages/database/
├── src/
│   ├── index.ts
│   └── queries.ts
├── src/queries.test.ts     ← Test with Miniflare D1
└── vitest.config.ts
```

In the workspace root `turbo.json`, add the test pipeline:
```json
{
  "tasks": {
    "test": {
      "dependsOn": ["^build"],
      "outputs": ["coverage/**"]
    }
  }
}
```

Run all tests: `pnpm turbo run test`
Run tests for a single package: `pnpm turbo run test --filter=@your-org/api`
Run in watch mode: `cd workers/api && pnpm vitest`

---

## Section 4 — Integration Tests for HTTP Routes

For full HTTP route testing, send real `Request` objects to the Worker's `fetch`
handler and assert on `Response` objects:

```typescript
import { env, createExecutionContext, waitOnExecutionContext }
  from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';
import worker from '../src/index';

async function callWorker(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const request = new Request(`https://api.example.com${path}`, init);
  const ctx = createExecutionContext();
  const response = await worker.fetch(request, env, ctx);
  await waitOnExecutionContext(ctx);
  return response;
}

describe('POST /users', () => {
  it('creates a user and returns 201', async () => {
    const response = await callWorker('/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'alice@example.com' }),
    });
    expect(response.status).toBe(201);
    const body = await response.json();
    expect(body.email).toBe('alice@example.com');
  });

  it('returns 400 for missing email', async () => {
    const response = await callWorker('/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    expect(response.status).toBe(400);
  });
});
```

This approach tests the full request handling stack including routing, middleware,
validation, and database interaction — in the real Workers runtime.

---

## Section 5 — CI Configuration

**GitHub Actions workflow:**
```yaml
name: Test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo run build
      - run: pnpm turbo run test
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        if: always()
        with:
          files: '**/coverage/lcov.info'
```

Add coverage thresholds to `vitest.config.ts` to enforce a floor:
```typescript
export default defineWorkersConfig({
  test: {
    coverage: {
      provider: 'v8',
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 70,
      },
    },
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

---

## Anti-patterns

- **Mocking Workers bindings with `vi.mock()`.** If you mock `env.MY_KV`, you are
  testing your mocks, not your code. Use Miniflare's real KV implementation. The whole
  point of `@cloudflare/vitest-pool-workers` is that you do not need to mock bindings.
- **Writing tests that depend on production KV or D1 IDs.** Tests must be isolated
  from production data. Use `[env.test]` in `wrangler.toml` to define separate test
  bindings, and never hard-code production resource IDs in test files.
- **Testing only the happy path.** Workers code is often the last line of defence
  before a response goes to a user. Test 400 validation errors, 401/403 auth failures,
  D1 `UNIQUE constraint failed` errors, KV not-found cases, and R2 object-not-found
  cases explicitly.
- **Running `wrangler dev` to manually verify every change.** Manual verification
  does not scale. If a test can cover it, write the test.
- **Skipping `waitOnExecutionContext(ctx)`.** If your Worker schedules async work via
  `ctx.waitUntil()`, you must call `waitOnExecutionContext(ctx)` in your test before
  asserting. Skipping it means your assertions run before the background work
  completes, producing flaky tests.

---

## Gotchas

- **`@cloudflare/vitest-pool-workers` requires Wrangler 3.x and Node.js 18+.** Pin
  the Wrangler version in `package.json` and enforce the Node.js version in your CI
  matrix.
- **D1 test instances are in-memory and reset between test files, not between tests.**
  If two tests in the same file write to D1, they see each other's data unless you
  clean up in `beforeEach`. Use `DELETE FROM table` or wrap tests in transactions.
- **Miniflare's KV is in-memory during tests.** This means KV tests are fast but
  they do not simulate the eventual consistency behaviour of production KV. Design
  tests that treat KV as immediately consistent, but design production code to handle
  eventual consistency.
- **Durable Objects in tests have their own in-memory storage.** Each Vitest worker
  process gets its own DO namespace. Tests for DO logic cannot share DO state across
  parallel test files without explicit coordination.
- **`compatibility_date` matters.** Tests use the compatibility flags from
  `wrangler.toml`. If your `compatibility_date` enables a new behaviour, your tests
  will use it. If production uses a different date, there may be divergence. Keep
  `compatibility_date` in sync between environments and review Cloudflare's
  compatibility flags changelog on upgrades.
- **Source maps for debugging test failures.** Configure `tsconfig.json` with
  `"sourceMap": true` so Vitest can report accurate line numbers in stack traces.
  Without source maps, a failing test points at minified output, not your TypeScript.

---

## Verification

A CI-ready test suite for a Cloudflare Workers project satisfies all of these:

- [ ] `pnpm vitest run` exits with code 0 on a clean main branch
- [ ] Tests cover all bindings used in the Worker (KV, D1, R2, etc.)
- [ ] Tests cover at least three error cases per route (not just happy path)
- [ ] `beforeEach` clears test data for any stateful binding (D1, KV)
- [ ] `waitOnExecutionContext(ctx)` is called in every test that involves a Worker
      fetch handler
- [ ] Coverage thresholds are enforced in CI (vitest coverage)
- [ ] Test bindings are defined in `[env.test]` and do not use production resource IDs
- [ ] Tests pass in CI on the same Node.js version as local development

---

## Related

- `flaky-tests-destroy-ci-trust.md`
- `developer-experience-dx-cloudflare-workers.md`
- `monorepo-pnpm-workspace-team-ownership.md`
- `cloudflare-storage-primitive-selection.md`
- `ai-agent-testing-2026.md`
- `works-on-my-machine-systematic-root-causes.md`

---

## Sources

- `@cloudflare/vitest-pool-workers`: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Miniflare 3: https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare
- Vitest: https://vitest.dev/
- Cloudflare Workers testing guide: https://developers.cloudflare.com/workers/testing/
- Workerd (open-source Workers runtime): https://github.com/cloudflare/workerd
