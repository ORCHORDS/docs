# Cloudflare Workers Testing with Vitest and Miniflare

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your Cloudflare Workers code passes Jest unit tests yet fails in production because `fetch`, `caches`, `KV`, and Durable Object bindings behave differently in Node.js than in the V8 isolate runtime. You need a test environment that executes your Worker code inside the same runtime it will run in during deployment — without deploying to Cloudflare on every PR.

---

## Context

Miniflare is an open-source, local Cloudflare Workers simulator that embeds the `workerd` runtime (the same engine Cloudflare uses). Vitest's pool system allows you to replace the default Node.js worker pool with a custom pool. The `@cloudflare/vitest-pool-workers` package wires these together: tests run in isolated `workerd` contexts, bindings are injected via `wrangler.toml`, and the full Workers API surface (`Request`, `Response`, `caches`, `KV`, `R2`, `D1`, `DurableObject`, `crypto`, `streams`) is available without shimming.

This approach differs from mocking: your Worker handler function is invoked through the real HTTP dispatch path, not through a stubbed function wrapper.

---

## Prerequisites

```
node >= 18
wrangler >= 3.78.0
@cloudflare/workers-types >= 4.x
@cloudflare/vitest-pool-workers >= 0.5.0
vitest >= 2.1.0
```

```bash
pnpm add -D vitest @cloudflare/vitest-pool-workers @cloudflare/workers-types wrangler
```

---

## Project Structure

```
packages/api-worker/
├── src/
│   ├── index.ts          # Worker entry point
│   └── handlers/
│       ├── auth.ts
│       └── items.ts
├── test/
│   ├── integration/
│   │   ├── auth.test.ts
│   │   └── items.test.ts
│   └── unit/
│       └── utils.test.ts
├── wrangler.toml
└── vitest.config.ts
```

---

## Section 1: Vitest Configuration

`vitest.config.ts` chooses the workers pool for integration tests while using the default Node pool for pure-unit tests:

```typescript
// packages/api-worker/vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersProject } from "@cloudflare/vitest-pool-workers/config";

export default defineConfig({
  test: {
    projects: [
      // Node pool — fast, no Workers globals needed
      {
        test: {
          name: "unit",
          include: ["test/unit/**/*.test.ts"],
          environment: "node",
        },
      },
      // workerd pool — full Workers runtime
      defineWorkersProject({
        test: {
          name: "integration",
          include: ["test/integration/**/*.test.ts"],
          poolOptions: {
            workers: {
              // Point at your wrangler.toml so bindings are available
              wrangler: { configPath: "./wrangler.toml" },
              // Optionally add test-only bindings
              miniflare: {
                kvNamespaces: ["TEST_KV"],
                r2Buckets: ["TEST_R2"],
              },
            },
          },
        },
      }),
    ],
  },
});
```

---

## Section 2: wrangler.toml for Testing

Declare bindings that match your production `wrangler.toml`. The test runner injects them:

```toml
# packages/api-worker/wrangler.toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"
compatibility_flags = ["nodejs_compat"]

[[kv_namespaces]]
binding = "SESSIONS"
id = "abc123"          # real ID for prod; test pool stubs it locally

[[d1_databases]]
binding = "DB"
database_name = "api-db"
database_id = "def456"

[vars]
ENVIRONMENT = "production"
```

For tests, declare a `[env.test]` stanza to override `ENVIRONMENT` and avoid hitting real remote resources:

```toml
[env.test]
[env.test.vars]
ENVIRONMENT = "test"
```

---

## Section 3: Writing Integration Tests

Use `SELF` (the bound Worker) for black-box handler tests, or import and call your handlers directly for white-box tests:

```typescript
// test/integration/items.test.ts
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeAll } from "vitest";

describe("GET /items", () => {
  beforeAll(async () => {
    // Seed D1 using the injected binding
    await env.DB.exec(`
      CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT);
      INSERT INTO items VALUES (1, 'widget');
    `);
  });

  it("returns 200 with item list", async () => {
    const response = await SELF.fetch("https://example.com/items");
    expect(response.status).toBe(200);
    const body = await response.json<{ items: { id: number; name: string }[] }>();
    expect(body.items).toHaveLength(1);
    expect(body.items[0].name).toBe("widget");
  });

  it("returns 404 for unknown item", async () => {
    const response = await SELF.fetch("https://example.com/items/999");
    expect(response.status).toBe(404);
  });
});
```

```typescript
// test/integration/auth.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import { verifyJwt } from "../../src/handlers/auth";

describe("verifyJwt", () => {
  it("rejects expired tokens", async () => {
    const expiredToken = "eyJ...";   // fixture
    const result = await verifyJwt(expiredToken, env);
    expect(result.valid).toBe(false);
    expect(result.reason).toBe("token_expired");
  });

  it("accepts valid tokens", async () => {
    // Workers crypto is available — sign with SubtleCrypto
    const key = await crypto.subtle.generateKey(
      { name: "HMAC", hash: "SHA-256" },
      true,
      ["sign", "verify"]
    );
    const token = await mintTestToken(key, { sub: "user-1" });
    const result = await verifyJwt(token, env, key);
    expect(result.valid).toBe(true);
  });
});
```

---

## Section 4: KV, R2, and Durable Object Bindings in Tests

Bindings declared in `miniflare` config are automatically provisioned in-memory:

```typescript
// test/integration/storage.test.ts
import { env } from "cloudflare:test";
import { it, expect } from "vitest";

it("writes to and reads from KV", async () => {
  await env.SESSIONS.put("sess-001", JSON.stringify({ userId: "u1" }));
  const raw = await env.SESSIONS.get("sess-001");
  expect(JSON.parse(raw!)).toMatchObject({ userId: "u1" });
});

it("uploads and retrieves from R2", async () => {
  await env.TEST_R2.put("file.txt", "hello world");
  const obj = await env.TEST_R2.get("file.txt");
  expect(await obj!.text()).toBe("hello world");
});
```

For Durable Objects, define a test-only stub or use `runInDurableObject`:

```typescript
import { runInDurableObject } from "cloudflare:test";

it("counter increments correctly", async () => {
  const id = env.COUNTER.idFromName("test-counter");
  const stub = env.COUNTER.get(id);
  await runInDurableObject(stub, async (instance) => {
    await instance.increment();
    expect(await instance.getCount()).toBe(1);
  });
});
```

---

## Section 5: CI Integration

Run integration and unit suites separately in GitHub Actions for caching and parallel execution:

```yaml
# .github/workflows/test.yml
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: "pnpm" }
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter api-worker test:unit

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: "pnpm" }
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter api-worker test:integration
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: vitest-report
          path: packages/api-worker/test-results/
```

```json
// packages/api-worker/package.json (scripts excerpt)
{
  "scripts": {
    "test": "vitest run",
    "test:unit": "vitest run --project unit",
    "test:integration": "vitest run --project integration",
    "test:watch": "vitest --project unit"
  }
}
```

---

## Section 6: TypeScript Configuration

Workers types must be scoped to integration tests only, since unit tests run in Node.js:

```jsonc
// packages/api-worker/tsconfig.json  — shared base
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

```jsonc
// packages/api-worker/tsconfig.test.json  — integration only
{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "types": ["@cloudflare/workers-types", "@cloudflare/vitest-pool-workers"]
  },
  "include": ["src", "test/integration"]
}
```

In `vitest.config.ts`, set the integration project's `tsconfig` path:

```typescript
defineWorkersProject({
  test: {
    // ...
    typecheck: { tsconfig: "./tsconfig.test.json" },
  },
}),
```

---

## Anti-patterns

- **Using Jest with manual Workers shims.** `globalThis.fetch` patches and `jest-environment-miniflare` are unmaintained. Use Vitest pool workers instead.
- **Mocking all bindings.** Stubs that return hardcoded values cannot surface binding-level bugs (TTL semantics, list pagination, D1 transaction rollbacks).
- **Running integration tests in watch mode against real remote KV.** Always use local Miniflare bindings in tests; remote bindings hit rate limits and leave orphaned test data.
- **Importing Node.js modules inside Worker code.** Even with `nodejs_compat`, some Node APIs behave differently. Let integration tests catch this early.

---

## Gotchas

- `SELF.fetch()` dispatches through the full Worker pipeline including middleware. If your Worker has rate-limiting middleware, tests will hit it unless you structure env differently.
- Miniflare's D1 is SQLite-backed and differs from Cloudflare's D1 in FTS5 support and `JSON_*` function availability. Avoid exotic SQLite extensions in schema migrations.
- `runInDurableObject` is only available for objects whose class is declared in `wrangler.toml`. Anonymous inline classes in tests are not supported.
- `env` from `cloudflare:test` is only available inside test files, not in source modules. Pass it as a parameter to the functions under test.
- `compatibility_date` must be identical between `wrangler.toml` and the pool config; mismatches cause subtle API behavior differences.

---

## Verification

```bash
# Run integration tests locally
pnpm --filter api-worker test:integration

# Run with verbose output and coverage
pnpm --filter api-worker exec vitest run --project integration --coverage

# Confirm workerd version in use
pnpm --filter api-worker exec vitest run --project integration 2>&1 | grep workerd

# Run a single test file
pnpm --filter api-worker exec vitest run test/integration/auth.test.ts
```

Expected: all integration tests pass, coverage report excludes Node-only paths, no "Cannot read properties of undefined" errors related to missing Workers globals.

---

## Related

- `github-actions-wrangler-deploy-pipeline.md` — deploy pipeline that gates on these tests
- `monorepo-pnpm-turborepo-2026.md` — running tests across packages in the monorepo
- `wrangler-environments-staging-production.md` — environment-specific `wrangler.toml` setup
- `cloudflare-workers-observability-tail-workers.md` — observability after tests pass and code ships

---

## Sources

- Cloudflare Docs: Vitest integration — https://developers.cloudflare.com/workers/testing/vitest-integration/
- `@cloudflare/vitest-pool-workers` README — https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- Miniflare v3 docs — https://miniflare.dev
- Vitest projects config — https://vitest.dev/guide/projects
