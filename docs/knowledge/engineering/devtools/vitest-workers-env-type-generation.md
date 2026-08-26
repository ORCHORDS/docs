# Generating and Testing Workers Environment Types with Vitest

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Vitest tests fail with `Property 'DB' does not exist on type 'Env'`, or you are manually maintaining a handwritten `Env` interface that keeps drifting out of sync with `wrangler.toml`. You want a single source of truth for environment bindings and you want CI to catch drift automatically.

## Context

`wrangler types` introspects `wrangler.toml` and generates a TypeScript declaration file (`worker-configuration.d.ts`) that exports an `Env` interface typed to match every binding — D1 databases, KV namespaces, R2 buckets, Durable Objects, secrets, and plain `vars`. Vitest tests running under `@cloudflare/vitest-pool-workers` can import that generated type and use `getMiniflareBindings()` to receive actual (in-process Miniflare) instances at test time.

## Type Generation and Test Setup

```typescript
// Step 1: generate the type file
// Run from the project root (same directory as wrangler.toml)
// npx wrangler types
// Creates: worker-configuration.d.ts

// worker-configuration.d.ts (generated — do not edit manually)
interface Env {
  DB: D1Database;
  KV: KVNamespace;
  ASSETS: R2Bucket;
  MY_DURABLE_OBJECT: DurableObjectNamespace;
  STRIPE_SECRET_KEY: string;  // from [vars] or secret placeholder
  ENVIRONMENT: string;
}

// vitest.config.ts
import { defineConfig } from 'vitest/config';
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        // miniflare options can override bindings for tests
        miniflare: {
          d1Databases: ['DB'],
          kvNamespaces: ['KV'],
          r2Buckets: ['ASSETS'],
        },
      },
    },
  },
});

// src/__tests__/user.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { env, createExecutionContext, waitOnExecutionContext } from 'cloudflare:test';
import type { Env } from '../../worker-configuration'; // generated type
import worker from '../index';

// TypeScript now knows env.DB is D1Database, env.KV is KVNamespace, etc.
const typedEnv = env as Env;

describe('User API', () => {
  beforeEach(async () => {
    // Seed the in-process D1 instance with a schema and fixture data
    await typedEnv.DB.exec(`
      CREATE TABLE IF NOT EXISTS users (
        id    INTEGER PRIMARY KEY,
        name  TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE
      );
    `);
    await typedEnv.DB
      .prepare('INSERT OR IGNORE INTO users (id, name, email) VALUES (?, ?, ?)')
      .bind(1, 'Alice', 'alice@example.com')
      .run();
  });

  it('returns a user by ID', async () => {
    const request = new Request('https://example.com/users/1');
    const ctx = createExecutionContext();
    const response = await worker.fetch(request, typedEnv, ctx);
    await waitOnExecutionContext(ctx);

    expect(response.status).toBe(200);
    const body = await response.json<{ name: string }>();
    expect(body.name).toBe('Alice');
  });

  it('returns 404 for unknown user', async () => {
    const request = new Request('https://example.com/users/999');
    const ctx = createExecutionContext();
    const response = await worker.fetch(request, typedEnv, ctx);
    await waitOnExecutionContext(ctx);
    expect(response.status).toBe(404);
  });

  it('puts and gets a KV value', async () => {
    await typedEnv.KV.put('greeting', 'hello');
    const value = await typedEnv.KV.get('greeting');
    expect(value).toBe('hello');
  });
});
```

## CI: Asserting the Type File Is Up to Date

```yaml
# .github/workflows/ci.yml
jobs:
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci

      - name: Regenerate Workers types
        run: npx wrangler types

      - name: Fail if type file is out of date
        run: |
          git diff --exit-code worker-configuration.d.ts || {
            echo "worker-configuration.d.ts is out of date."
            echo "Run 'npx wrangler types' locally and commit the result."
            exit 1
          }

      - name: Type-check
        run: npx tsc --noEmit

      - name: Run Vitest
        run: npx vitest run
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Overriding Bindings for Specific Tests

```typescript
// For a test that needs a fresh, isolated DB schema (no shared state)
import { runInDurableObject } from 'cloudflare:test';
// or simply use a transaction that is always rolled back:

beforeEach(async () => {
  // Wipe the table before each test for isolation
  await typedEnv.DB.exec('DELETE FROM users;');
});

// For KV, the in-process namespace is reset automatically between test files
// by the vitest-pool-workers pool. No manual teardown needed.
```

## `getMiniflareBindings()` — Legacy API Note

In `@cloudflare/vitest-pool-workers` v0.5+, the recommended import is from `cloudflare:test`:

```typescript
// Modern (v0.5+)
import { env } from 'cloudflare:test';

// Legacy — still works but deprecated in newer pool versions
import { getMiniflareBindings } from '@miniflare/tre';
const { DB, KV } = getMiniflareBindings<Env>();
```

Prefer the `cloudflare:test` import. It is type-aware and will be aligned with the stable Workers test API.

## Anti-patterns

- **Editing `worker-configuration.d.ts` manually.** The file is fully regenerated on each `wrangler types` run. Any manual edit is silently overwritten. Put custom types in a separate `src/types.ts`.
- **Importing `Env` from a handwritten interface in `src/index.ts`.** The handwritten version drifts from `wrangler.toml`. Always import from the generated file.
- **Running Vitest without `@cloudflare/vitest-pool-workers`.** Node-native Vitest does not emulate the Workers runtime globals (`caches`, `crypto`, Workers-specific fetch semantics). Tests may pass locally and fail in production.
- **Using `process.env` in tests to supply binding values.** Bindings are not environment variables in the Workers model. Use `typedEnv.SECRET_KEY` (which resolves to the value in `wrangler.toml`'s `[vars]` section for tests).

## Gotchas

- `wrangler types` requires a valid `wrangler.toml` with `account_id` set, or `CLOUDFLARE_ACCOUNT_ID` in the environment. It makes a lightweight API call to resolve D1 and KV binding metadata.
- The generated file uses `interface Env`, not `type Env`. This matters for declaration merging if you want to extend it elsewhere.
- Secrets defined with `wrangler secret put` do **not** appear in `wrangler.toml`, so `wrangler types` generates them as `string` placeholders only if you list them under `[vars]` with empty string values as documentation. Add a comment noting the actual value comes from the secret store.
- D1 migrations are not automatically run in Miniflare. You must run `CREATE TABLE` DDL statements in `beforeEach` / `beforeAll` or point Miniflare at your migrations directory via `d1Persist` config.

## Verification

```bash
# Generate types
npx wrangler types
cat worker-configuration.d.ts

# Run tests
npx vitest run --reporter=verbose

# Check for drift (will exit 1 if file changed and was not committed)
git diff --exit-code worker-configuration.d.ts && echo "Types are up to date"
```

## Related

- `wrangler-secret-bulk-import-workers.md` — managing secrets referenced in the generated `Env`
- `wrangler-dev-external-api-mock-proxy.md` — overriding binding URLs in local dev
- `typescript-path-aliases-workers-monorepo.md` — resolving path aliases in the same Vitest setup

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#types
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
