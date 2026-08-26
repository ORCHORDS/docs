# Miniflare v4 Migration Guide

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Miniflare v4 ships with Wrangler 4 and introduces a new `WorkerOptions` API, drops the legacy `MiniflareOptions` flat config, and removes the `compat_date` auto-inference that older test suites relied on. Teams upgrading from Miniflare v3 (Wrangler 3.x) encounter type errors and silent test failures when `compatibility_date` is not set or when bindings are constructed with the old shape.

## Context

Miniflare v4 is the local simulation layer that Wrangler 4's `wrangler dev` and Vitest's `@cloudflare/vitest-pool-workers` both use under the hood. The public API surface moved from a class instantiated directly (`new Miniflare({ ... })`) to one where most consumers configure it via `wrangler.toml` and the pool config, reserving the programmatic API for advanced integration test setups. The key breaking changes are: `KVNamespace` option key rename, `R2Bucket` binding key changes, removal of `globals`, and the mandatory `compatibilityDate` field.

## v3 vs v4 Config Diff

```typescript
// BEFORE — Miniflare v3
import { Miniflare } from "miniflare";

const mf = new Miniflare({
  modules: true,
  script: `export default { fetch() { return new Response("ok"); } }`,
  kvNamespaces: ["MY_KV"],           // v3: array of strings
  r2Buckets: ["MY_BUCKET"],          // v3: array of strings
  d1Databases: ["MY_DB"],            // v3: array of strings
  globals: { MY_GLOBAL: "value" },   // v3: globals injection (removed)
  compatDate: "2024-01-01",          // v3 alias (removed in v4)
});

// AFTER — Miniflare v4
import { Miniflare } from "miniflare";

const mf = new Miniflare({
  modules: true,
  script: `export default { fetch() { return new Response("ok"); } }`,
  // v4: bindings object replaces separate arrays
  bindings: {
    MY_CONSTANT: "value",            // replaces globals
  },
  kvNamespaces: { MY_KV: "my-kv" }, // v4: object — name → persistence key
  r2Buckets: { MY_BUCKET: "my-r2" },
  d1Databases: { MY_DB: "my-d1" },
  compatibilityDate: "2026-01-01",   // v4: required, no alias
  compatibilityFlags: ["nodejs_compat"],
});
```

## Full Integration Test Setup with v4

```typescript
// tests/integration/setup.ts
import { Miniflare, Response as MiniflareResponse } from "miniflare";
import { afterAll, beforeAll } from "vitest";
import { readFileSync } from "node:fs";

let mf: Miniflare;

export async function getMiniflare(): Promise<Miniflare> {
  return mf;
}

beforeAll(async () => {
  const script = readFileSync("dist/index.js", "utf-8");

  mf = new Miniflare({
    modules: true,
    script,
    compatibilityDate: "2026-08-01",
    compatibilityFlags: ["nodejs_compat"],

    // v4 D1 — pass migrations so the in-memory database is seeded
    d1Databases: { DB: "test-db" },
    d1Migrations: [
      { name: "0001_init", sql: readFileSync("migrations/0001_init.sql", "utf-8") },
    ],

    // v4 KV — keys are binding names, values are namespace IDs for persistence
    kvNamespaces: { CACHE: "test-cache" },

    // v4 R2
    r2Buckets: { UPLOADS: "test-uploads" },

    // Plain environment variables (replaces v3 globals)
    bindings: {
      API_TOKEN: "test-token",
      ENVIRONMENT: "test",
    },

    // v4: port 0 = assign random port (avoids conflicts in parallel test runs)
    port: 0,
  });

  await mf.ready;
});

afterAll(async () => {
  await mf.dispose();
});
```

## Vitest Pool Config for Miniflare v4

```typescript
// vitest.config.integration.ts
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

// Use defineWorkersConfig for tests that need real Workers bindings
export default defineWorkersConfig({
  test: {
    include: ["tests/integration/**/*.test.ts"],
    poolOptions: {
      workers: {
        wrangler: {
          // Pool reads wrangler.toml for binding definitions
          configPath: "./wrangler.toml",
        },
        miniflare: {
          // Override specific settings for the test environment
          compatibilityDate: "2026-08-01",
          compatibilityFlags: ["nodejs_compat"],
          bindings: {
            ENVIRONMENT: "test",
            API_TOKEN: "test-token",
          },
        },
      },
    },
  },
});
```

## Migrating D1 Seed Patterns

```typescript
// tests/integration/helpers/seed.ts
import type { D1Database } from "@cloudflare/workers-types";

// v3: used mf.getD1Database("DB") — v4: same method, but type changed
export async function seedUsers(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare("INSERT INTO users (id, name) VALUES (?, ?)").bind("1", "Alice"),
    db.prepare("INSERT INTO users (id, name) VALUES (?, ?)").bind("2", "Bob"),
  ]);
}

// In tests:
// import { SELF } from "cloudflare:test";
// import { env } from "cloudflare:test";
// await seedUsers(env.DB);
// const res = await SELF.fetch("https://example.com/api/users");
```

## Anti-patterns

- Passing `compatDate` (the v3 alias) in a v4 `Miniflare` constructor — it is silently ignored; the Worker uses a default compatibility date that may differ from production, causing subtle behavioural differences.
- Reusing a single `Miniflare` instance across test files in parallel Vitest runs — each file should construct its own isolated instance, or use `@cloudflare/vitest-pool-workers` which manages isolation automatically.
- Setting `d1Databases` as an array of strings in v4 — this was valid in v3, but v4 requires an object mapping binding names to persistence IDs; an array input causes a TypeScript error and is ignored at runtime.

## Gotchas

- Miniflare v4's in-memory D1 database does not persist between `Miniflare` instantiations. If you rely on data from a previous test run, you must re-seed in `beforeAll`. This is intentional — test isolation.
- The `mf.getWorker()` API was removed in v4. To make requests, use `mf.dispatchFetch()` or the pool's injected `SELF` export from `cloudflare:test`.
- `mf.ready` is a `Promise<void>` in v4, replacing the v3 pattern of `await mf.getKVNamespace()` to implicitly wait for initialisation. Always `await mf.ready` before dispatching test requests.

## Verification

```bash
# Check installed Miniflare version
pnpm ls miniflare

# Run integration tests with the v4 pool
pnpm vitest run --config vitest.config.integration.ts

# Confirm D1 seed by querying after setup
pnpm wrangler d1 execute DB --local --command "SELECT COUNT(*) FROM users"

# Type-check the test helpers against v4 types
pnpm tsc --project tsconfig.test.json --noEmit
```

## Related

- `devtools/miniflare-custom-plugins-bindings.md`
- `devtools/vitest-workers-miniflare-testing-setup.md`
- `devtools/wrangler-dev-local-d1-r2-kv.md`

## Sources

- https://github.com/cloudflare/workers-sdk/blob/main/packages/miniflare/CHANGELOG.md
- https://developers.cloudflare.com/workers/testing/vitest-integration/get-started/write-your-first-test/
- https://developers.cloudflare.com/workers/wrangler/migration/migrating-from-wrangler-3/
