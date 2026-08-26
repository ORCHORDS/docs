# Wrangler unstable_dev Programmatic API Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Integration tests need to start a real Wrangler dev server, send HTTP requests to it, and assert
responses — all without shelling out to `wrangler dev` manually or managing a long-lived process
in CI. The `wrangler` package exposes `unstable_dev` (and its stable successor `getPlatformProxy`)
as a programmatic API for exactly this use case, but its lifecycle, typing, and teardown semantics
catch teams off-guard, leaving dangling processes and flaky test suites.

## Context

`unstable_dev` starts an in-process local Worker server (backed by Miniflare under the hood)
and returns a `Worker` handle with a `.fetch()` method. You call it, the Worker processes the
request in the local runtime, and you get back a real `Response`. No HTTP port required; the
handle proxies the request through the in-process channel.

In Wrangler 3+ the stable equivalent is `getPlatformProxy`, but `unstable_dev` is still the
primary integration-test entry point as of 2026 because it actually runs the Worker script, while
`getPlatformProxy` only provides binding implementations.

The `Worker` handle must be torn down via `.stop()` after every test suite; failing to do so
leaves the Miniflare process alive, which causes port conflicts and memory leaks in CI.

## 1. Install and Import

```bash
npm install --save-dev wrangler
```

```typescript
// src/integration/setup.ts
import { unstable_dev } from "wrangler";
import type { UnstableDevWorker } from "wrangler";

export async function startWorker(): Promise<UnstableDevWorker> {
  return unstable_dev(
    // Path to the Worker entry point (must match `main` in wrangler.toml)
    "src/index.ts",
    {
      // Inherit bindings and compatibility settings from wrangler.toml
      config: "wrangler.toml",
      // Do not open a browser tab
      experimental: { disableExperimentalWarning: true },
      // Disable live-reload watcher — we don't need it in tests
      watch: false,
      // Keep the log level low to reduce test output noise
      logLevel: "error",
      // Use local mode (Miniflare) — no network calls to Cloudflare
      local: true,
    }
  );
}
```

## 2. Basic Integration Test with Vitest

```typescript
// src/integration/worker.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { startWorker } from "./setup";
import type { UnstableDevWorker } from "wrangler";

describe("Worker integration", () => {
  let worker: UnstableDevWorker;

  beforeAll(async () => {
    worker = await startWorker();
  }, 30_000); // generous timeout for first-time Miniflare startup

  afterAll(async () => {
    await worker.stop();
  });

  it("GET / returns 200 with HTML body", async () => {
    const response = await worker.fetch("/");
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toContain("text/html");
    const text = await response.text();
    expect(text).toContain("Hello Worker");
  });

  it("POST /echo reflects JSON body", async () => {
    const response = await worker.fetch("/echo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ msg: "hello" }),
    });
    expect(response.status).toBe(200);
    const json = await response.json<{ msg: string }>();
    expect(json.msg).toBe("hello");
  });

  it("returns 404 for unknown routes", async () => {
    const response = await worker.fetch("/does-not-exist");
    expect(response.status).toBe(404);
  });
});
```

## 3. Passing Environment Variables and Bindings Inline

```typescript
// src/integration/bindings.test.ts
import { unstable_dev } from "wrangler";
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import type { UnstableDevWorker } from "wrangler";

describe("Worker with KV binding", () => {
  let worker: UnstableDevWorker;

  beforeAll(async () => {
    worker = await unstable_dev("src/kv-worker.ts", {
      config: "wrangler.toml",
      local: true,
      logLevel: "error",
      // Inline variables override wrangler.toml [vars] for tests
      vars: {
        ENVIRONMENT: "test",
        FEATURE_FLAG: "true",
      },
      // KV namespace is automatically backed by an in-memory store
      // when running in local mode — no wrangler.toml entry needed.
    });
  }, 30_000);

  afterAll(async () => { await worker.stop(); });

  it("reads ENVIRONMENT var from handler", async () => {
    const response = await worker.fetch("/env");
    const { environment } = await response.json<{ environment: string }>();
    expect(environment).toBe("test");
  });
});
```

## 4. Parallel Worker Instances for Service Binding Tests

```typescript
// src/integration/service-binding.test.ts
import { unstable_dev } from "wrangler";
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import type { UnstableDevWorker } from "wrangler";

describe("Gateway Worker + Auth Worker service binding", () => {
  let authWorker: UnstableDevWorker;
  let gatewayWorker: UnstableDevWorker;

  beforeAll(async () => {
    // Start the upstream auth worker first
    authWorker = await unstable_dev("packages/auth/src/index.ts", {
      config: "packages/auth/wrangler.toml",
      local: true,
      logLevel: "error",
    });

    // Start the gateway and wire the auth worker address in as a service binding
    gatewayWorker = await unstable_dev("packages/gateway/src/index.ts", {
      config: "packages/gateway/wrangler.toml",
      local: true,
      logLevel: "error",
      experimental: {
        // Point the service binding at the already-started auth worker
        serviceBindings: {
          AUTH: async (request: Request) => authWorker.fetch(request),
        },
      },
    });
  }, 60_000);

  afterAll(async () => {
    // Stop in reverse dependency order
    await gatewayWorker.stop();
    await authWorker.stop();
  });

  it("gateway proxies auth check to auth worker", async () => {
    const response = await gatewayWorker.fetch("/protected", {
      headers: { Authorization: "Bearer valid" },
    });
    expect(response.status).toBe(200);
  });

  it("gateway rejects when auth worker returns 401", async () => {
    const response = await gatewayWorker.fetch("/protected"); // no auth header
    expect(response.status).toBe(401);
  });
});
```

## 5. Timeout and Retry Strategy for Slow CI Runners

Miniflare cold-start time varies by runner. Wrap startup with a helper that retries on timeout:

```typescript
// src/integration/helpers.ts
import { unstable_dev } from "wrangler";
import type { UnstableDevWorker, UnstableDevOptions } from "wrangler";

export async function startWorkerWithRetry(
  script: string,
  options: UnstableDevOptions,
  retries = 3
): Promise<UnstableDevWorker> {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const worker = await Promise.race<UnstableDevWorker>([
        unstable_dev(script, options),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("unstable_dev startup timeout")), 25_000)
        ),
      ]);
      return worker;
    } catch (err) {
      console.error(`[startWorker] attempt ${attempt} failed:`, err);
      if (attempt === retries) throw err;
      await new Promise((r) => setTimeout(r, 2_000));
    }
  }
  throw new Error("unreachable");
}
```

## 6. Asserting Durable Object Interactions

```typescript
// src/integration/durable-object.test.ts
import { unstable_dev } from "wrangler";
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import type { UnstableDevWorker } from "wrangler";

describe("Counter Durable Object", () => {
  let worker: UnstableDevWorker;

  beforeAll(async () => {
    worker = await unstable_dev("src/counter.ts", {
      config: "wrangler.toml",
      local: true,
      logLevel: "error",
    });
  }, 30_000);

  afterAll(async () => { await worker.stop(); });

  it("increments counter across two requests to same DO stub", async () => {
    // First request — initializes counter at 0, increments to 1
    const r1 = await worker.fetch("/counter/room-42", { method: "POST" });
    expect(await r1.json<{ count: number }>()).toEqual({ count: 1 });

    // Second request — same DO instance, persists in-memory across requests
    const r2 = await worker.fetch("/counter/room-42", { method: "POST" });
    expect(await r2.json<{ count: number }>()).toEqual({ count: 2 });
  });
});
```

## Anti-patterns

- **Calling `unstable_dev` inside `it()` blocks** — each test spins up a new Miniflare instance;
  use `beforeAll` / `afterAll` and share a single instance per `describe` block.
- **Not calling `worker.stop()`** — Miniflare processes accumulate in CI, consuming memory and
  ports until the runner is killed.
- **Using `unstable_dev` for unit tests** — it is an integration tool; unit tests should use
  `@cloudflare/vitest-pool-workers` directly for speed.
- **Setting `watch: true` in test config** — the file watcher stays alive and prevents the
  process from exiting cleanly after the test suite finishes.

## Gotchas

- `unstable_dev` is still prefixed with `unstable_` as of Wrangler 3.x; the API surface is
  considered stable for testing purposes but Cloudflare reserves the right to change internals.
- D1 databases in local mode are ephemeral per `unstable_dev` instance; run migrations inside
  `beforeAll` against the returned `worker` environment to populate schema.
- The `worker.fetch()` call signature mirrors the `fetch()` Web API but the first argument
  accepts a path string OR a full `Request` object — avoid mixing the two in the same test file.
- On Apple Silicon (arm64), the bundled Miniflare binary may need a Rosetta 2 prefix; pin
  `wrangler` to a version that ships an arm64 build (`>= 3.50`).

## Verification

```bash
# Run integration tests in isolation (separate vitest project to avoid pool conflicts)
npx vitest run --project integration

# Check for zombie Miniflare processes after test failure
ps aux | grep miniflare

# Confirm worker starts and responds within 30 s on a cold runner
time npx tsx src/integration/smoke.ts
```

## Related

- `wrangler-dev-local-d1-r2-kv.md`
- `miniflare-durable-objects-fake-clock-testing.md`
- `vitest-workers-miniflare-testing-setup.md`
- `wrangler-service-bindings-multi-worker-local-dev.md`
- `workers-runtime-compatibility-date-testing-strategy.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/api/#unstable_dev
- https://github.com/cloudflare/workers-sdk/blob/main/packages/wrangler/src/api/dev.ts
- https://developers.cloudflare.com/workers/testing/integration-tests/
- https://miniflare.dev/
