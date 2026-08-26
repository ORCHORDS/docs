# Integration Testing Workers with Service Bindings in Miniflare

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have multiple Cloudflare Workers that call each other via service bindings and need to verify end-to-end data flow in a local test environment without deploying to Cloudflare's network.

## Context

Service bindings allow one Worker to call another Worker directly, without going over the public internet. Testing this locally requires Miniflare's multi-Worker support, where you declare all Workers and their binding relationships in configuration, then run assertions against the composite system.

Miniflare 3.x (shipped inside `wrangler` and `@cloudflare/vitest-pool-workers`) supports multi-Worker setups via programmatic API or config files. Each Worker can have its own isolated KV, D1, Queues, and R2 bindings backed by `InMemoryStorage`.

## Miniflare Multi-Worker Setup with Service Bindings

```typescript
import {
  Miniflare,
  Response,
  InMemoryStorage,
} from "miniflare";
import { describe, it, beforeEach, afterEach, expect } from "vitest";

let mf: Miniflare;

beforeEach(async () => {
  mf = new Miniflare({
    // Enable multi-Worker mode
    workers: [
      {
        name: "outer-worker",
        scriptPath: "./src/outer-worker.ts",
        modules: true,
        bindings: {
          QUEUE_BINDING: { type: "queue", queueName: "task-queue" },
          KV_STORE: { type: "kv", id: "kv-outer" },
        },
        serviceBindings: {
          // Bind to the inner Worker by name
          INNER_SERVICE: "inner-worker",
        },
      },
      {
        name: "inner-worker",
        scriptPath: "./src/inner-worker.ts",
        modules: true,
        bindings: {
          DB: { type: "d1", databaseName: "inner-db" },
        },
        queueConsumers: {
          "task-queue": { maxBatchSize: 10, maxWaitMs: 100 },
        },
      },
    ],
    // InMemoryStorage for all Workers' bindings
    kvPersist: false,
    d1Persist: false,
    queuesPersist: false,
  });

  // Seed inner Worker's D1 schema
  const innerEnv = await mf.getWorkerEnv("inner-worker");
  await (innerEnv.DB as D1Database).exec(`
    CREATE TABLE IF NOT EXISTS tasks (
      id    TEXT PRIMARY KEY,
      state TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT NOT NULL
    );
  `);
});

afterEach(async () => {
  await mf.dispose();
});

describe("outer -> inner service binding flow", () => {
  it("outer Worker proxies a request to inner Worker and gets a response", async () => {
    const outerUrl = await mf.getWorkerUrl("outer-worker");
    const res = await mf.dispatchFetch(
      new Request(`${outerUrl}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskId: "t-001", payload: "hello" }),
      }),
      { workerId: "outer-worker" }
    );

    expect(res.status).toBe(202);
    const body = await res.json<{ queued: boolean }>();
    expect(body.queued).toBe(true);
  });

  it("cross-Worker data flow: outer enqueues task, inner consumer updates D1", async () => {
    // Trigger outer Worker to enqueue a task
    await mf.dispatchFetch(
      new Request("http://outer/dispatch", {
        method: "POST",
        body: JSON.stringify({ taskId: "t-002", payload: "work" }),
        headers: { "Content-Type": "application/json" },
      }),
      { workerId: "outer-worker" }
    );

    // Flush the queue so the inner consumer processes the batch
    await mf.flushQueues();

    // Verify inner Worker wrote the task state to D1
    const innerEnv = await mf.getWorkerEnv("inner-worker");
    const db = innerEnv.DB as D1Database;
    const row = await db
      .prepare("SELECT state FROM tasks WHERE id = ?")
      .bind("t-002")
      .first<{ state: string }>();

    expect(row?.state).toBe("completed");
  });

  it("outer Worker KV write is isolated from inner Worker KV", async () => {
    const outerEnv = await mf.getWorkerEnv("outer-worker");
    const kv = outerEnv.KV_STORE as KVNamespace;
    await kv.put("meta:last-run", "2026-08-24");

    // Inner Worker has no KV_STORE binding — confirm env separation
    const innerEnv = await mf.getWorkerEnv("inner-worker");
    expect((innerEnv as Record<string, unknown>).KV_STORE).toBeUndefined();
  });
});
```

## Defining Workers Programmatically vs. Config File

The programmatic API shown above is preferred for test suites because it lets you inject per-test configuration. For shared dev environments, a `wrangler.toml` with `[[services]]` entries is simpler:

```toml
# wrangler.toml (outer-worker)
name = "outer-worker"
main = "src/outer-worker.ts"

[[services]]
binding = "INNER_SERVICE"
service = "inner-worker"
```

Miniflare reads `wrangler.toml` automatically when you pass `configPath` instead of the inline `workers` array.

## Resetting Storage Between Tests

Call `mf.dispose()` in `afterEach` and recreate the `Miniflare` instance in `beforeEach`. This is simpler and more reliable than selectively clearing keys:

```typescript
// Prefer full teardown over manual key deletion
afterEach(async () => {
  await mf.dispose(); // tears down all in-memory storage
});
```

If `Miniflare` construction is slow, cache the instance and only reset storage:

```typescript
const kv = outerEnv.KV_STORE as KVNamespace;
const { keys } = await kv.list();
await Promise.all(keys.map((k) => kv.delete(k.name)));
```

## Anti-patterns

- **Sharing one `Miniflare` instance across all tests without teardown** — state bleeds between tests, causing false positives.
- **Using real Cloudflare account resources** in unit/integration tests — slow, requires network, incurs costs.
- **Forgetting to call `mf.flushQueues()`** after enqueuing — the queue consumer never runs and D1 assertions fail silently.
- **Hard-coding Worker script paths** without resolving from project root — tests break in CI when the working directory differs.

## Gotchas

- `mf.getWorkerEnv()` returns the bindings object but NOT a full `ExecutionContext`. You cannot call `ctx.waitUntil()` on it directly.
- `mf.dispatchFetch()` requires the `workerId` option when multiple Workers are present; otherwise Miniflare dispatches to the first Worker defined.
- Queue consumers only fire after `mf.flushQueues()` — they do not process automatically in real-time during tests.
- Service binding calls made from within a Worker script are intercepted by Miniflare and routed to the declared target Worker, but the target must be fully initialised before the first request.

## Verification

```bash
# Run integration tests
npx vitest run src/**/*.integration.test.ts

# Confirm all Workers are resolved
npx wrangler dev --local --port 8787
curl -X POST http://localhost:8787/dispatch -d '{"taskId":"smoke","payload":"test"}'
# Expected: {"queued":true}
```

## Related

- `vitest-workers-kv-namespace-isolation.md`
- `playwright-workers-authenticated-session-testing.md`
- Miniflare API docs — `https://miniflare.dev/get-started/api`

## Sources

- Miniflare 3 multi-Worker documentation
- Cloudflare Workers service bindings guide
- `@cloudflare/vitest-pool-workers` README
