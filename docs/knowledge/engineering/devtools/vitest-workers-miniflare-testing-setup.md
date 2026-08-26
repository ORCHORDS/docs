# Vitest Workers & Miniflare Testing Setup

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Unit tests that pass in Node.js fail at runtime in a Cloudflare Worker
because APIs like `crypto.subtle`, `Request`/`Response`, D1, and KV
are missing or behave differently. Mocking them manually is fragile
and drifts from the real runtime over time.

## Context

`@cloudflare/vitest-pool-workers` runs each test file inside a real
Miniflare v3 Worker sandbox rather than in Node.js. D1, KV, R2, and
Durable Object bindings are injected as in-memory stubs. The pool is
configured via `wrangler.vitest.config.ts` and standard `vitest.config.ts`
is pointed at it with `pool: 'workers'`. Requires Wrangler ≥ 3.78 and
Vitest ≥ 1.5.

## 1. Installing the pool

```bash
npm install --save-dev \
  @cloudflare/vitest-pool-workers \
  vitest
```

Add a pool-specific config at the project root:

```ts
// wrangler.vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

Then in `vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    pool: "@cloudflare/vitest-pool-workers",
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

Run with:

```bash
npx vitest --pool=workers
```

## 2. Testing the fetch handler with SELF

`SELF` is a special binding that dispatches requests directly into the
current Worker under test without a network round-trip.

```ts
import { SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("fetch handler", () => {
  it("returns 200 for /health", async () => {
    const res = await SELF.fetch("http://example.com/health");
    expect(res.status).toBe(200);
  });

  it("returns JSON body", async () => {
    const res = await SELF.fetch("http://example.com/api/ping");
    const body = await res.json<{ ok: boolean }>();
    expect(body.ok).toBe(true);
  });
});
```

The Worker entry-point is resolved from `wrangler.toml → main`.
No extra mocking is needed; the real handler runs.

## 3. D1 in-memory binding in tests

Declare the D1 database in `wrangler.toml` as usual. The pool creates
an in-memory SQLite instance for each test worker thread.

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id   = "local"
migrations_dir = "migrations"
```

In the test, access the binding via the `env` export from
`cloudflare:test`:

```ts
import { env } from "cloudflare:test";

it("inserts a user row", async () => {
  await env.DB.exec(`CREATE TABLE IF NOT EXISTS users
    (id INTEGER PRIMARY KEY, name TEXT)`);
  const result = await env.DB.prepare(
    "INSERT INTO users (name) VALUES (?)"
  ).bind("alice").run();
  expect(result.success).toBe(true);
});
```

Run migrations before the suite with a `beforeAll`:

```ts
import { env } from "cloudflare:test";
import { readFileSync } from "node:fs";

beforeAll(async () => {
  const sql = readFileSync("migrations/0001_init.sql", "utf8");
  await env.DB.exec(sql);
});
```

## 4. KV mock

KV namespaces declared in `wrangler.toml` are available as in-memory
maps. No network calls occur.

```ts
import { env } from "cloudflare:test";

it("stores and retrieves a value", async () => {
  await env.MY_KV.put("session:abc", JSON.stringify({ uid: 1 }));
  const raw = await env.MY_KV.get("session:abc");
  expect(JSON.parse(raw!)).toEqual({ uid: 1 });
});
```

## 5. Testing Durable Objects

Durable Objects require `isolatedStorage: true` in the pool config to
prevent state leaking between tests.

```ts
// wrangler.vitest.config.ts
export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        isolatedStorage: true,
      },
    },
  },
});
```

Get a stub via `env`:

```ts
import { env } from "cloudflare:test";

it("counter increments", async () => {
  const id = env.COUNTER.idFromName("test-counter");
  const stub = env.COUNTER.get(id);
  const res = await stub.fetch("http://do/increment");
  expect(await res.text()).toBe("1");
});
```

## Anti-patterns

- Running the full suite under Node.js pool and only smoke-testing
  one file under workers — misses binding-level failures early.
- Using `vi.mock()` for KV or D1 — produces fake stubs that diverge
  from the real Miniflare behaviour (e.g., metadata TTL, SQL types).
- Sharing mutable D1 state across `it()` blocks without `beforeEach`
  resets — order-dependent test failures that are hard to reproduce.
- Forgetting `migrations_dir` in wrangler.toml — the in-memory DB
  starts empty and all schema queries fail with "no such table".

## Gotchas

- `SELF.fetch` uses the Worker's configured `compatibility_date`. If
  your tests rely on newer APIs, bump the date in `wrangler.toml`.
- `env` from `cloudflare:test` is only available inside the workers
  pool; importing it in a Node pool throws at module resolution time.
- Vitest `--reporter=verbose` hides Miniflare console logs by default.
  Set `MINIFLARE_LOG=info` in the environment to surface them.
- D1 `exec()` runs the SQL as a batch; multi-statement strings work,
  but semicolons inside string literals must be escaped carefully.

## Verification

```bash
# Run workers-pool tests only
npx vitest run --pool=workers

# Check coverage (requires v8 provider)
npx vitest run --pool=workers --coverage.provider=v8

# Print Miniflare internal logs
MINIFLARE_LOG=info npx vitest run --pool=workers
```

Expected output: all D1/KV/DO tests green, no "no such table" errors.

## Related

- `wrangler dev --test` for integration testing against a local dev
  server with real Cloudflare network calls intercepted.
- `@cloudflare/workers-types` for TypeScript types matching the runtime.
- Miniflare v3 source for understanding in-memory behaviour differences.

## Source URLs (verified 2026-08-17)

https://developers.cloudflare.com/workers/testing/vitest-integration/
https://developers.cloudflare.com/workers/testing/vitest-integration/get-started/
https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
https://miniflare.dev/
