# Vitest Workers Module Mocking and Inject Pattern

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You need to replace a module imported by your Worker handler — an analytics client, a secrets helper, an external SDK — during Vitest tests without modifying the production source. `jest.mock()` patterns from Node test suites do not work verbatim in `@cloudflare/vitest-pool-workers` because the Workers runtime runs in a separate V8 isolate, not the Node process running Vitest itself.

---

## Context

`@cloudflare/vitest-pool-workers` exposes three complementary mechanisms for module replacement:

1. **`vi.mock()`** — intercepts a module specifier and replaces its exports with a factory or auto-mock (same API as Vitest/Jest, but executed in the workers isolate).
2. **`inject()`** from `cloudflare:test`** — injects a typed value into a binding slot (env vars, KV namespaces, D1 databases) from the test file, so the Worker sees a fake implementation.
3. **`unstable_dev` / service bindings mock** — replaces an entire Worker service binding with a hand-rolled `fetch` handler.

This article covers patterns 1 and 2. Pattern 3 is covered in `wrangler-service-bindings-multi-worker-local-dev.md`.

Stack:

- `@cloudflare/vitest-pool-workers` ^0.5
- `vitest` ^2.0
- `wrangler` ^4.0

---

## vi.mock() in a Workers Isolate

`vi.mock()` works the same way as in Node: the call is hoisted to the top of the test file by Vitest's transform, and the factory runs before any imports are evaluated.

```ts
// src/analytics.ts  (module being mocked)
export async function trackEvent(name: string, props: Record<string, unknown>) {
  await fetch("https://analytics.example.com/track", {
    method: "POST",
    body: JSON.stringify({ name, props }),
  });
}
```

```ts
// src/handler.ts
import { trackEvent } from "./analytics";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    await trackEvent("page_view", { url: request.url });
    return new Response("ok");
  },
};
```

```ts
// src/handler.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SELF } from "cloudflare:test";

// Must use the same specifier as in handler.ts
vi.mock("./analytics", () => ({
  trackEvent: vi.fn().mockResolvedValue(undefined),
}));

// Import AFTER vi.mock so the mocked version is used
import { trackEvent } from "./analytics";

describe("handler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls trackEvent on every request", async () => {
    const res = await SELF.fetch("https://worker.test/");
    expect(res.status).toBe(200);
    expect(trackEvent).toHaveBeenCalledOnce();
    expect(trackEvent).toHaveBeenCalledWith("page_view", {
      url: "https://worker.test/",
    });
  });
});
```

---

## Partial Module Mocking

Replace only some exports while keeping real implementations for others:

```ts
vi.mock("./analytics", async (importOriginal) => {
  const real = await importOriginal<typeof import("./analytics")>();
  return {
    ...real,
    // Replace only trackEvent; keep all other exports real
    trackEvent: vi.fn().mockResolvedValue(undefined),
  };
});
```

---

## inject() for Env Bindings

`inject()` from `cloudflare:test` lets you override a binding in `env` without touching `wrangler.toml`. It is typed against your `Env` interface, so mismatched bindings cause a compile error.

```ts
// src/kv-handler.test.ts
import { env, inject } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { SELF } from "cloudflare:test";

// Define a fake KV namespace
const fakeKV: KVNamespace = {
  async get(key: string) {
    if (key === "greeting") return "Hello from mock KV";
    return null;
  },
  async put() {},
  async delete() {},
  async list() {
    return { keys: [], list_complete: true, cacheStatus: null };
  },
  async getWithMetadata() {
    return { value: null, metadata: null, cacheStatus: null };
  },
};

describe("KV handler", () => {
  beforeEach(() => {
    // Inject replaces the binding for the duration of this test suite
    inject({ MY_KV: fakeKV });
  });

  it("returns greeting from KV", async () => {
    const res = await SELF.fetch("https://worker.test/greeting");
    expect(await res.text()).toBe("Hello from mock KV");
  });
});
```

---

## Combining vi.mock() and inject()

A common pattern: mock the module that wraps the SDK, and separately inject a fake binding for the raw primitive it reads from:

```ts
import { inject } from "cloudflare:test";
import { vi } from "vitest";
import type { D1Database } from "@cloudflare/workers-types";

// Fake D1 that returns a fixed row
const fakeD1 = {
  prepare: (query: string) => ({
    bind: (...params: unknown[]) => ({
      first: async () => ({ id: 1, name: "Alice" }),
      all: async () => ({ results: [{ id: 1, name: "Alice" }], success: true, meta: {} }),
      run: async () => ({ success: true, meta: {} }),
    }),
    first: async () => ({ id: 1, name: "Alice" }),
    all: async () => ({ results: [], success: true, meta: {} }),
    run: async () => ({ success: true, meta: {} }),
  }),
  dump: async () => new ArrayBuffer(0),
  batch: async (stmts: D1PreparedStatement[]) => [],
  exec: async (sql: string) => ({ count: 0, duration: 0 }),
} as unknown as D1Database;

// Mock the ORM layer on top
vi.mock("./db/queries", () => ({
  getUserById: vi.fn().mockResolvedValue({ id: 1, name: "Alice" }),
}));

beforeEach(() => {
  inject({ DB: fakeD1 });
});
```

---

## Mocking globalThis in the Workers Isolate

To mock browser/Worker globals like `fetch` itself:

```ts
import { vi, beforeEach, afterEach } from "vitest";

const mockFetch = vi.fn();

beforeEach(() => {
  // Replace the global fetch in the Workers isolate
  vi.stubGlobal("fetch", mockFetch);
  mockFetch.mockResolvedValue(new Response("mocked", { status: 200 }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it("uses the stubbed fetch", async () => {
  const res = await SELF.fetch("https://worker.test/external-call");
  expect(mockFetch).toHaveBeenCalled();
});
```

---

## Anti-patterns

- **Calling `vi.mock()` inside `beforeEach`**: Vitest hoists `vi.mock()` to file-top at parse time; calling it inside lifecycle hooks has no effect. Always place it at the module's top level.
- **Importing the mocked module before `vi.mock()`**: The hoisting handles this at compile time, but if you use dynamic `import()` inside the test body, the factory may not have run yet — use `vi.importMock()` for dynamic cases.
- **Using `jest.mock()` syntax**: `@cloudflare/vitest-pool-workers` does not shim the `jest` global. Use `vi` exclusively.
- **Injecting a binding for the wrong type**: `inject({ MY_KV: fakeD1 })` compiles only if `Env["MY_KV"]` is `D1Database`. TypeScript catches mismatches at compile time if you keep `Env` in sync with `wrangler.toml`.
- **Forgetting `vi.clearAllMocks()` in `beforeEach`**: Mock call counts persist across tests in the same file, causing false positives on `toHaveBeenCalledOnce()`.

---

## Gotchas

- `inject()` scopes its override to the current test file; it does not survive across Worker restart boundaries (each test file gets its own isolate instance).
- `vi.mock()` paths are resolved relative to the test file, not the Worker entry point. Use the same relative path that the handler itself uses.
- If the module you are mocking has side effects at import time (e.g., registers a listener), those side effects still run before the factory replaces the exports unless you mock all exported symbols.
- `SELF` dispatches through the real Worker dispatch loop and picks up the injected env. If you call the handler function directly (bypassing `SELF`), you must pass the injected env manually.
- `vi.stubGlobal("fetch", ...)` only affects the Workers isolate's global scope — the Miniflare internal fetch (used for binding I/O) is a different codepath and is not stubbed.

---

## Verification

```bash
# Run with verbose output to confirm mock call assertions
pnpm vitest run --reporter=verbose src/handler.test.ts

# Type-check that inject() bindings match Env
pnpm tsc --noEmit
```

---

## Related

- `vitest-pool-workers-cloudflare-test-api.md`
- `vitest-workers-miniflare-testing-setup.md`
- `vitest-workers-queue-batch-testing.md`
- `msw-external-api-mocking-workers-tests.md`
- `hono-test-utils-workers-unit-testing.md`
- `wrangler-service-bindings-multi-worker-local-dev.md`

---

## Sources

- Vitest `vi.mock()` API: https://vitest.dev/api/vi.html#vi-mock
- `@cloudflare/vitest-pool-workers` inject: https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/#inject
- Workers testing guide: https://developers.cloudflare.com/workers/testing/vitest-integration/
- `vi.stubGlobal`: https://vitest.dev/api/vi.html#vi-stubglobal
