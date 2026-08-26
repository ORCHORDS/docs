# KV Namespace Isolation Between Vitest Test Suites in @cloudflare/vitest-pool-workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Vitest test suites that share a single KV namespace see each other's keys and produce flaky, order-dependent failures. You need each test file — and ideally each test — to operate against a completely fresh KV namespace with no residual data from other suites.

## Context

`@cloudflare/vitest-pool-workers` runs each test file in a separate Worker isolate backed by Miniflare. By default, KV namespaces declared in `vitest.config.ts` are shared across all workers in the pool. Adding a unique suffix per test file or per test forces Miniflare to create a separate in-memory namespace for each scope.

The same pattern applies to D1 databases and R2 buckets — the `createIsolatedEnv()` helper below covers all three.

## KV Namespace Isolation Implementation

```typescript
// src/test-utils/isolated-env.ts
import { Miniflare, InMemoryStorage } from "miniflare";
import crypto from "node:crypto";

export interface IsolatedEnv {
  kv: KVNamespace;
  db: D1Database;
  r2: R2Bucket;
  dispose: () => Promise<void>;
}

/**
 * Creates fresh KV, D1, and R2 bindings backed by independent in-memory
 * storage. Call once per test (in beforeEach) or once per suite (in beforeAll)
 * depending on the isolation level you need.
 */
export async function createIsolatedEnv(): Promise<IsolatedEnv> {
  const suffix = crypto.randomBytes(6).toString("hex"); // e.g. "a3f9c1"

  const mf = new Miniflare({
    script: `
      export default {
        async fetch(request, env) {
          return new Response('ok');
        }
      };
    `,
    modules: true,
    kvNamespaces: [`TEST_KV_${suffix}`],
    d1Databases: [`TEST_DB_${suffix}`],
    r2Buckets: [`TEST_R2_${suffix}`],
    kvPersist: false,
    d1Persist: false,
    r2Persist: false,
  });

  const env = await mf.getBindings<{
 | D1Database | R2Bucket;
  }>();

  return {
    kv: env[`TEST_KV_${suffix}`] as KVNamespace,
    db: env[`TEST_DB_${suffix}`] as D1Database,
    r2: env[`TEST_R2_${suffix}`] as R2Bucket,
    dispose: () => mf.dispose(),
  };
}

// ---------------------------------------------------------------------------
// Cleanup helper — use when reusing an env across multiple tests in a suite
// ---------------------------------------------------------------------------

export async function clearKV(kv: KVNamespace): Promise<void> {
  let cursor: string | undefined;
  do {
    const list = await kv.list({ cursor, limit: 100 });
    await Promise.all(list.keys.map((k) => kv.delete(k.name)));
    cursor = list.list_complete ? undefined : list.cursor;
  } while (cursor);
}
```

```typescript
// src/feature-a.test.ts  — per-test isolation (strictest)
import { describe, it, beforeEach, afterEach, expect } from "vitest";
import { createIsolatedEnv, IsolatedEnv } from "./test-utils/isolated-env";

let env: IsolatedEnv;

beforeEach(async () => {
  env = await createIsolatedEnv();
});

afterEach(async () => {
  await env.dispose();
});

describe("feature-a KV writes", () => {
  it("stores a value under a key", async () => {
    await env.kv.put("greeting", "hello");
    const value = await env.kv.get("greeting");
    expect(value).toBe("hello");
  });

  it("starts empty — no contamination from previous test", async () => {
    const value = await env.kv.get("greeting");
    // A fresh namespace: this key does NOT exist from the previous test
    expect(value).toBeNull();
  });
});
```

```typescript
// src/feature-b.test.ts  — per-suite isolation (faster, acceptable for read-heavy suites)
import { describe, it, beforeAll, afterAll, beforeEach, expect } from "vitest";
import {
  createIsolatedEnv,
  clearKV,
  IsolatedEnv,
} from "./test-utils/isolated-env";

let env: IsolatedEnv;

beforeAll(async () => {
  env = await createIsolatedEnv();
  // Apply schema migrations once per suite
  await env.db.exec(`
    CREATE TABLE IF NOT EXISTS items (
      id TEXT PRIMARY KEY,
      value TEXT
    );
  `);
});

afterAll(async () => {
  await env.dispose();
});

beforeEach(async () => {
  // Reset KV between tests within the suite without recreating Miniflare
  await clearKV(env.kv);
  await env.db.exec("DELETE FROM items;");
});

describe("feature-b combined KV + D1", () => {
  it("writes KV and D1 in the same test", async () => {
    await env.kv.put("counter", "1");
    await env.db
      .prepare("INSERT INTO items (id, value) VALUES (?, ?)")
      .bind("i-001", "alpha")
      .run();

    const counter = await env.kv.get("counter");
    const row = await env.db
      .prepare("SELECT value FROM items WHERE id = ?")
      .bind("i-001")
      .first<{ value: string }>();

    expect(counter).toBe("1");
    expect(row?.value).toBe("alpha");
  });
});
```

## vitest.config.ts Pool Configuration

```typescript
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        // Each test FILE runs in its own isolated Worker context
        isolatedStorage: true,
      },
    },
  },
});
```

## Performance Comparison

| Strategy | Miniflare instances | Teardown overhead | Isolation level |
|---|---|---|---|
| Per-test `createIsolatedEnv()` | 1 per test | ~50 ms | Strictest |
| Per-suite `createIsolatedEnv()` + `clearKV` | 1 per file | ~5 ms per test | Suite-level |
| Pool-level `isolatedStorage: true` | 1 per file (pool) | Near zero | File-level |

For suites with 50+ tests, prefer per-suite isolation with `clearKV` — the Miniflare startup cost is paid once, and manual KV clearing is fast.

## Anti-patterns

- **Using a static KV namespace name** (e.g. `TEST_KV`) across all test files — parallel Vitest workers share state and cause intermittent failures.
- **Not awaiting `env.dispose()`** in `afterEach`/`afterAll` — leaked Miniflare instances accumulate open handles and cause Vitest to hang after the test run.
- **Deleting keys one at a time in a loop without pagination** — `kv.list()` returns at most 1000 keys per call; use the `cursor` field for large namespaces.
- **Mixing per-test and per-suite isolation in the same file** — pick one strategy per test file and document it clearly.

## Gotchas

- `@cloudflare/vitest-pool-workers` with `isolatedStorage: true` already isolates storage per file via a different mechanism (snapshot/reset). Adding your own `createIsolatedEnv()` on top of that is fine but redundant for KV; use one or the other.
- KV `list()` does not return keys with TTL metadata unless you pass `{ withMetadata: true }` — the `clearKV` helper above works without it because we only need key names.
- `mf.getBindings()` returns the bindings as a plain object; TypeScript does not know the binding types at compile time — cast explicitly as shown.

## Verification

```bash
# Run all test suites in parallel
npx vitest run

# Confirm no cross-suite contamination by running a single file twice
npx vitest run src/feature-a.test.ts src/feature-a.test.ts

# Profile Miniflare startup overhead
time npx vitest run --reporter=verbose src/feature-b.test.ts
```

## Related

- `workers-integration-test-service-bindings-miniflare.md`
- `contract-testing-workers-pact-provider-verification.md`
- Miniflare `InMemoryStorage` API reference

## Sources

- `@cloudflare/vitest-pool-workers` documentation
- Miniflare 3.x programmatic API
- Vitest pool workers configuration guide
