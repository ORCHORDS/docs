# Testing Workers with @cloudflare/vitest-pool-workers and cloudflare:test

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You want to write unit tests for a Cloudflare Worker that run inside the real `workerd` runtime, giving access to `env` bindings, `SELF.fetch`, `waitUntil`, and Durable Object stubs without mocking the platform.

## Context
`@cloudflare/vitest-pool-workers` replaces the older Miniflare test helper by running each Vitest worker thread inside a real `workerd` isolate. Tests import from `cloudflare:test` to access `env`, `SELF`, `createExecutionContext`, and `waitOnExecutionContext`. This is distinct from the basic Miniflare setup; it provides higher-fidelity coverage of platform APIs like KV, D1, R2, and Durable Objects without starting a full dev server.

## Installation and vitest.config.ts

Install the pool and configure Vitest to use it:

```bash
pnpm add -D @cloudflare/vitest-pool-workers vitest
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        // Expose miniflare options for bindings not in wrangler.toml
        miniflare: {
          compatibilityDate: "2025-10-01",
          compatibilityFlags: ["nodejs_compat"],
        },
      },
    },
    // Ensures test files run inside the workerd context
    globals: true,
  },
});
```

## Writing env-aware Tests with cloudflare:test

Import test utilities directly from the `cloudflare:test` virtual module:

```typescript
// src/index.test.ts
import {
  env,
  createExecutionContext,
  waitOnExecutionContext,
  SELF,
} from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import worker from "./index";

// env is typed from the wrangler.toml bindings at build time
declare module "cloudflare:test" {
  interface ProvidedEnv {
    KV_STORE: KVNamespace;
    DB: D1Database;
    ENVIRONMENT: string;
  }
}

describe("worker env bindings", () => {
  beforeEach(async () => {
    // Seed KV before each test; env.KV_STORE is a real in-process KV
    await env.KV_STORE.put("greeting", "hello");
  });

  it("reads KV value in the handler", async () => {
    const ctx = createExecutionContext();
    const request = new Request("https://example.com/greet");
    const response = await worker.fetch(request, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("hello");
  });
});
```

## Testing Fetch Handlers via SELF

`SELF` provides a fetch handle that routes through your worker's full handler chain, useful for integration-style tests that cover routing middleware:

```typescript
// src/router.test.ts
import { SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("router integration", () => {
  it("returns 404 for unknown routes", async () => {
    const response = await SELF.fetch("https://example.com/does-not-exist");
    expect(response.status).toBe(404);
  });

  it("handles POST /items with JSON body", async () => {
    const response = await SELF.fetch("https://example.com/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "widget" }),
    });
    expect(response.status).toBe(201);
    const body = await response.json<{ id: string }>();
    expect(body.id).toBeTruthy();
  });
});
```

## Testing Scheduled Handlers

Trigger cron events using the `SELF.scheduled` method available on the pool:

```typescript
// src/cron.test.ts
import { env, createScheduledController, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import worker from "./index";
import { it, expect } from "vitest";

it("processes scheduled cron job", async () => {
  // Write a sentinel before running the cron
  await env.KV_STORE.put("last-run", "");

  const ctrl = createScheduledController({ scheduledTime: Date.now(), cron: "0 * * * *" });
  const ctx = createExecutionContext();
  await worker.scheduled(ctrl, env, ctx);
  await waitOnExecutionContext(ctx);

  const lastRun = await env.KV_STORE.get("last-run");
  expect(lastRun).not.toBe("");
});
```

## Testing Durable Objects

Durable Object stubs are available through `env` when the binding is declared in `wrangler.toml`:

```typescript
// src/counter.test.ts
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("Counter Durable Object", () => {
  it("increments and returns count", async () => {
    const id = env.COUNTER.idFromName("test-counter");
    const stub = env.COUNTER.get(id);

    const inc = await stub.fetch("https://do/increment");
    expect(await inc.json<{ count: number }>()).toEqual({ count: 1 });

    const get = await stub.fetch("https://do/value");
    expect(await get.json<{ count: number }>()).toEqual({ count: 1 });
  });

  it("isolates state between named instances", async () => {
    const idA = env.COUNTER.idFromName("a");
    const idB = env.COUNTER.idFromName("b");

    await env.COUNTER.get(idA).fetch("https://do/increment");
    const bVal = await env.COUNTER.get(idB).fetch("https://do/value");
    expect(await bVal.json<{ count: number }>()).toEqual({ count: 0 });
  });
});
```

## Testing D1 with Migrations

Apply schema before tests using D1's `exec` API:

```typescript
// test/setup.ts
import { env } from "cloudflare:test";
import { readFileSync } from "node:fs";

export async function applyMigrations() {
  const sql = readFileSync("./migrations/0001_initial.sql", "utf8");
  await env.DB.exec(sql);
}
```

```typescript
// src/users.test.ts
import { env } from "cloudflare:test";
import { beforeAll, it, expect } from "vitest";
import { applyMigrations } from "../test/setup";
import { createUser, getUser } from "./users";

beforeAll(async () => {
  await applyMigrations();
});

it("creates and retrieves a user", async () => {
  await createUser(env.DB, { email: "alice@example.com" });
  const user = await getUser(env.DB, "alice@example.com");
  expect(user?.email).toBe("alice@example.com");
});
```

## Anti-patterns
- Using `vi.mock("cloudflare:workers")` to stub `env`; the pool provides real bindings — mocking them defeats the purpose.
- Sharing mutable KV/D1 state across parallel test files without per-test cleanup; use `beforeEach` to reset seeded data.
- Importing Node.js-only modules (e.g. `fs`) directly in worker source files; they must go through `nodejs_compat` flag and are unavailable in the `cloudflare:test` context for worker code.
- Skipping `waitOnExecutionContext`; omitting this lets `waitUntil` promises escape and causes flaky assertions.
- Running this pool alongside Jest or a standard Vitest environment in the same config without workspace separation.

## Gotchas
- The `cloudflare:test` module is only resolvable inside the pool worker thread, not in regular Node.js vitest workers; mixing environments in one config causes `Cannot find module 'cloudflare:test'` errors.
- `SELF.fetch` requires the worker's `fetch` export to be the default export; named exports are not auto-routed.
- D1 `exec` does not support multiple semicolon-separated statements in all compatibility dates; split migrations per statement when targeting older dates.
- Durable Object alarm testing requires `miniflare.runDurableObjectAlarms` set to `true` in pool options.
- Type augmentation of `ProvidedEnv` must be in a `.d.ts` or a test file loaded before the test; it has no runtime effect.

## Verification
```bash
pnpm vitest run --reporter=verbose
# Look for "workerd" in the pool name line, confirming tests ran in the real runtime
pnpm vitest run --coverage
```

## Related
- `/documentation/docs/policies/devtools/vitest-workers-miniflare-testing-setup.md`
- `/documentation/docs/policies/devtools/hono-test-utils-workers-unit-testing.md`
- `/documentation/docs/policies/devtools/miniflare-v4-migration-guide.md`
- `/documentation/docs/policies/devtools/wrangler-dev-local-d1-r2-kv.md`

## Sources
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/
