# Mocking Workers Service Bindings in Vitest

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Cloudflare Worker calls another Worker via a service binding (`env.MY_SERVICE.fetch()`), and you need to unit-test the calling Worker in isolation without spinning up the real downstream service. You want typed mock helpers, deterministic `Response` objects, and clean mock state between tests.

---

## Context
`@cloudflare/vitest-pool-workers` runs tests inside a real Miniflare v3 sandbox, giving you access to the actual `env` object that the Worker runtime injects. Service bindings are represented as `Fetcher` objects on `env`, which means you can replace them with plain objects that satisfy the `Fetcher` interface — specifically an object with a `fetch` method typed to return `Promise<Response>`. Vitest's `vi.fn()` creates a spy that you can configure per-test with `mockResolvedValueOnce`, then restore with `afterEach(() => vi.restoreAllMocks())`. This keeps every test hermetic.

---

## Setup / Config

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[services]]
binding = "MY_SERVICE"
service = "downstream-worker"
```

```toml
# vitest.config.ts (pool config excerpt)
# vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          serviceBindings: {
            // Replaced per-test; value here is a no-op placeholder
            MY_SERVICE: async () => new Response("placeholder", { status: 200 }),
          },
        },
      },
    },
  },
});
```

## Implementation

```typescript
// src/index.ts — the Worker under test
export interface Env {
  MY_SERVICE: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/proxy") {
      const downstream = await env.MY_SERVICE.fetch(
        new Request("https://downstream/api/data", {
          method: "POST",
          body: JSON.stringify({ source: "my-worker" }),
          headers: { "Content-Type": "application/json" },
        })
      );

      if (!downstream.ok) {
        return new Response("Upstream error", { status: 502 });
      }

      const data = await downstream.json();
      return Response.json({ proxied: data });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## Testing

```typescript
// src/index.test.ts
import {
  env,
  createExecutionContext,
  waitOnExecutionContext,
  SELF,
} from "cloudflare:test";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import type { Env } from "./index";

// Typed helper so every test gets a correctly shaped mock
function mockService(response: Response): { fetch: ReturnType<typeof vi.fn> } {
  const fetchSpy = vi.fn().mockResolvedValue(response);
  return { fetch: fetchSpy };
}

describe("Worker service binding mock", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("proxies a successful downstream response", async () => {
    const downstreamPayload = { result: "ok", count: 42 };
    const mock = mockService(
      Response.json(downstreamPayload, { status: 200 })
    );

    // Cast env to Env so TypeScript is happy, then replace binding
    (env as unknown as Env).MY_SERVICE = mock as unknown as Fetcher;

    const request = new Request("https://example.com/proxy", {
      method: "GET",
    });
    const ctx = createExecutionContext();
    const { default: worker } = await import("./index");
    const response = await worker.fetch(request, env as unknown as Env, ctx);
    await waitOnExecutionContext(ctx);

    expect(response.status).toBe(200);
    const body = await response.json<{ proxied: typeof downstreamPayload }>();
    expect(body.proxied).toEqual(downstreamPayload);

    // Assert the downstream was called with the correct URL and body
    expect(mock.fetch).toHaveBeenCalledOnce();
    const [calledRequest] = mock.fetch.mock.calls[0] as [Request];
    expect(calledRequest.url).toBe("https://downstream/api/data");
    expect(calledRequest.method).toBe("POST");

    const calledBody = await calledRequest.json<{ source: string }>();
    expect(calledBody.source).toBe("my-worker");
  });

  it("returns 502 when downstream fails", async () => {
    const mock = mockService(new Response("Service unavailable", { status: 503 }));
    (env as unknown as Env).MY_SERVICE = mock as unknown as Fetcher;

    const request = new Request("https://example.com/proxy");
    const ctx = createExecutionContext();
    const { default: worker } = await import("./index");
    const response = await worker.fetch(request, env as unknown as Env, ctx);
    await waitOnExecutionContext(ctx);

    expect(response.status).toBe(502);
    expect(mock.fetch).toHaveBeenCalledOnce();
  });

  it("does not call downstream for unknown paths", async () => {
    const mock = mockService(new Response("Should not be called", { status: 200 }));
    (env as unknown as Env).MY_SERVICE = mock as unknown as Fetcher;

    const request = new Request("https://example.com/unknown");
    const ctx = createExecutionContext();
    const { default: worker } = await import("./index");
    const response = await worker.fetch(request, env as unknown as Env, ctx);
    await waitOnExecutionContext(ctx);

    expect(response.status).toBe(404);
    expect(mock.fetch).not.toHaveBeenCalled();
  });
});
```

---

## Anti-patterns
- **Sharing a single mock instance across tests** — each `it()` block should call `mockService()` freshly; shared spies accumulate call counts and `mockResolvedValueOnce` queues unexpectedly drain.
- **Casting `env.MY_SERVICE` to `any` without typing** — use the `Env` interface so the compiler catches signature drift when the real binding changes.
- **Not awaiting `waitOnExecutionContext`** — async tasks scheduled inside the handler (e.g. `ctx.waitUntil(...)`) won't finish before your assertions run.
- **Using `vi.mock()` at module level for service bindings** — service bindings live on `env`, not on a module; `vi.fn()` on the env property is the correct interception point.

---

## Gotchas
- The `Fetcher` type is a Cloudflare global; import it from `@cloudflare/workers-types` if TypeScript can't resolve it in test files.
- `vi.restoreAllMocks()` only restores spies created with `vi.spyOn`; spies created with `vi.fn()` must be cleared manually with `mockReset()` or by recreating them each test.
- Pool workers share a module cache — use dynamic `import()` inside each test or call `vi.resetModules()` if your Worker has module-level state.
- `SELF.fetch()` goes through the full Worker runtime and re-reads `env` from Miniflare; direct `worker.fetch(request, env, ctx)` calls bypass that and let you inject the mock env directly.

---

## Verification

```bash
# Run only service binding tests
npx vitest run src/index.test.ts

# Run with verbose output to see call counts
npx vitest run --reporter=verbose src/index.test.ts

# Watch mode during development
npx vitest --reporter=verbose src/index.test.ts
```

---

## Related
- `workers-integration-test-d1-seed-fixtures.md`
- `workers-test-queue-consumer-mock-batch.md`

---

## Sources
- Cloudflare Vitest Pool Workers docs — https://developers.cloudflare.com/workers/testing/vitest-integration/
- Vitest mock functions — https://vitest.dev/api/mock.html
