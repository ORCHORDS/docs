# GitHub Actions Integration Testing with @cloudflare/vitest-pool-workers (Miniflare)

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Worker unit tests using standard Node.js mocks diverge from real runtime behaviour — fetch semantics, caches API, Durable Objects, KV, R2. You want CI to run tests directly inside a Miniflare sandbox (via `@cloudflare/vitest-pool-workers`) so tests execute against the actual Workers runtime, not a mocked approximation, without requiring a Cloudflare account for every CI run.

## Context

`@cloudflare/vitest-pool-workers` runs Vitest worker threads inside a Workerd (Miniflare 3) instance. Tests import from `cloudflare:test` to access the Workers runtime context and can bind KV namespaces, D1 databases, R2 buckets, Durable Objects, and environment variables — all in-memory, no network calls to Cloudflare. This is distinct from:
- `vitest-coverage-threshold` (coverage gates on existing test output)
- `vitest-test-sharding-workers` (splitting test suites across runners)

The focus here is on **configuring the pool, wiring bindings, and running the CI job** correctly.

## Step 1 — Install and Configure the Vitest Pool

```bash
npm install --save-dev vitest @cloudflare/vitest-pool-workers wrangler
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    globals: true,
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          // Override bindings for test isolation
          kvNamespaces: ["SESSION_KV", "CACHE_KV"],
          d1Databases: ["DB"],
          r2Buckets: ["ASSETS"],
          durableObjects: {
            COUNTER: "CounterDO",
          },
          bindings: {
            ENVIRONMENT: "test",
            API_KEY: "test-api-key-not-real",
          },
        },
      },
    },
    // Keep each test file isolated in its own Workerd sandbox
    isolateStorage: true,
  },
});
```

## Step 2 — Write a Test Using cloudflare:test Helpers

```typescript
// src/handlers/session.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { env, createExecutionContext, waitOnExecutionContext, SELF } from "cloudflare:test";
import { app } from "../app";

// IncomingRequestCfProperties is provided by @cloudflare/workers-types
declare module "cloudflare:test" {
  interface ProvidedEnv {
    SESSION_KV: KVNamespace;
    DB: D1Database;
    ENVIRONMENT: string;
    API_KEY: string;
  }
}

beforeEach(async () => {
  // Seed KV before each test — storage is reset per-test (isolateStorage: true)
  await env.SESSION_KV.put("user:1", JSON.stringify({ name: "Alice", role: "admin" }));
  // Seed D1
  await env.DB.exec(`CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)`);
  await env.DB.prepare("INSERT INTO users VALUES (1, 'Alice')").run();
});

describe("GET /session/:id", () => {
  it("returns user from KV", async () => {
    const ctx = createExecutionContext();
    const request = new Request("http://worker.test/session/1", {
      headers: { "X-Api-Key": "test-api-key-not-real" },
    });
    const response = await app.fetch(request, env, ctx);
    await waitOnExecutionContext(ctx);
    expect(response.status).toBe(200);
    const body = await response.json<{ name: string }>();
    expect(body.name).toBe("Alice");
  });

  it("returns 404 for missing session", async () => {
    const ctx = createExecutionContext();
    const response = await app.fetch(
      new Request("http://worker.test/session/999"),
      env,
      ctx
    );
    await waitOnExecutionContext(ctx);
    expect(response.status).toBe(404);
  });
});
```

## Step 3 — GitHub Actions CI Workflow

```yaml
# .github/workflows/integration-test.yml
name: Workers integration tests (Miniflare)
on:
  pull_request:
  push:
    branches: [main]

jobs:
  integration-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - name: Install dependencies
        run: npm ci

      # wrangler generates types from wrangler.toml bindings
      - name: Generate Workers runtime types
        run: npx wrangler types
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Run integration tests
        run: npx vitest run --reporter=verbose --reporter=github-actions
        timeout-minutes: 10

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: vitest-results
          path: test-results/
          retention-days: 7
```

## Step 4 — Caching node_modules and Workerd Binary

```yaml
      - name: Cache node_modules
        uses: actions/cache@v4
        with:
          path: |
            ~/.npm
            node_modules
          key: ${{ runner.os }}-node-22-${{ hashFiles('package-lock.json') }}
          restore-keys: |
            ${{ runner.os }}-node-22-

      # Workerd binary is downloaded into node_modules/.workerd during npm ci.
      # The node_modules cache above covers it, but if using a separate cache:
      - name: Cache workerd binary
        uses: actions/cache@v4
        with:
          path: node_modules/workerd
          key: workerd-${{ runner.os }}-${{ hashFiles('node_modules/workerd/package.json') }}
```

## Step 5 — Parallel Job Split for Large Test Suites

```yaml
  integration-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - run: npm ci
      - run: npx wrangler types
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      - name: Run shard ${{ matrix.shard }}/4
        run: npx vitest run --shard=${{ matrix.shard }}/4 --reporter=github-actions
        timeout-minutes: 8
```

## Anti-patterns

- **Using `@miniflare/...` v2 packages directly**: Miniflare v3 is embedded in `@cloudflare/vitest-pool-workers`; importing the old package produces incompatible APIs and incorrect behaviour for newer Workers features.
- **Setting `environment: 'node'` in vitest.config**: The pool overrides the environment; explicitly setting `node` disables the Workerd sandbox and breaks `cloudflare:test` imports.
- **Calling real Cloudflare APIs inside tests**: The Miniflare sandbox runs entirely in-memory. Any `fetch` to `api.cloudflare.com` goes to the real network. Use `vi.mock` or stub `fetch` in the test for external calls.
- **Not using `isolateStorage: true`**: Without it, KV/D1 state bleeds between test files and creates non-deterministic test ordering dependencies.

## Gotchas

- `wrangler types` requires a valid `CLOUDFLARE_API_TOKEN` to resolve remote bindings like AI, Vectorize, and Analytics Engine. For offline CI, use `--env-interface` override or skip for projects with only local-emulatable bindings.
- Durable Object classes must be exported from the worker entry point — the pool cannot discover them from a non-exported class.
- `waitOnExecutionContext(ctx)` is required before asserting on side effects (KV writes, D1 inserts) initiated from within a handler, because Workers use a deferred execution model for `ctx.waitUntil`.
- The `--reporter=github-actions` flag emits `::error` annotations for failing tests directly in the Actions log; combine with `--reporter=verbose` for local debugging parity.
- The Workerd binary requires `linux/amd64`; `ubuntu-latest` (x86-64) is fine. ARM-based runners (`ubuntu-24.04-arm`) need the `linux/arm64` workerd binary — check that `workerd` npm package provides it for your pin version.

## Verification

```bash
# Run a single test file locally with the pool active
npx vitest run src/handlers/session.test.ts --reporter=verbose

# Confirm Workerd is being used (not Node pool)
npx vitest run --reporter=verbose 2>&1 | grep -i "workerd\|miniflare"
```

## Related

- `github-actions-vitest-test-sharding-workers.md`
- `github-actions-vitest-coverage-threshold-gate.md`
- `github-actions-cloudflare-d1-migration-pipeline.md`
- `github-actions-wrangler-d1-seeding-preview-environment.md`
- `github-actions-kv-namespace-seeding-preview.md`

## Sources

- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/workers/testing/vitest-integration/configuration/
- https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/
- https://miniflare.dev/
- https://vitest.dev/guide/test-sharding
