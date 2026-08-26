# Testing Cloudflare Workers Service Bindings with Vitest

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You have a Cloudflare Workers architecture where a gateway Worker calls downstream Workers via service bindings — an auth Worker, a pricing Worker, a notification Worker. When you test the gateway in isolation the downstream calls hit real Workers or error out entirely. You want fast, deterministic unit and integration tests that verify: the gateway forwards the right requests, handles error responses from downstream, and correctly propagates headers — without deploying every downstream Worker.

---

## Context

Service bindings (`services` in `wrangler.toml`) give a Worker a typed `Fetcher` that calls another Worker in the same account with zero-latency, no public internet exposure, and full-duplex streaming. From a testing angle this is a seam: you can swap the real downstream Worker for a controlled double.

Miniflare 3.x (the local runtime inside `vitest-pool-workers`) supports service bindings in two ways:

1. **Another local Worker** — Miniflare can wire together two in-memory Workers, giving you true end-to-end integration tests.
2. **A hand-rolled `Fetcher` stub** — you construct a `Fetcher`-shaped object and inject it into `env`, giving you pure isolation.

Both strategies are valuable; the right choice depends on whether you are testing the gateway's logic (use a stub) or the end-to-end integration of two services (use a second local Worker).

---

## 1. Project Setup

```
npm install --save-dev vitest @cloudflare/vitest-pool-workers wrangler
```

`wrangler.toml` (gateway Worker):

```toml
name = "gateway"
main = "src/gateway.ts"
compatibility_date = "2025-01-01"

[[services]]
binding = "AUTH"
service = "auth-worker"

[[services]]
binding = "PRICING"
service = "pricing-worker"
```

`vitest.config.ts`:

```typescript
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          isolatedStorage: true,
          // Provide stub Workers for service bindings
          workers: [
            {
              name: "auth-worker",
              modules: true,
              script: `
                export default {
                  fetch(req) {
                    // Default stub: 200 authenticated
                    return new Response(JSON.stringify({ userId: "u_test" }), {
                      headers: { "content-type": "application/json" }
                    });
                  }
                }
              `,
            },
            {
              name: "pricing-worker",
              modules: true,
              script: `
                export default {
                  fetch() {
                    return new Response(JSON.stringify({ price: 9.99 }), {
                      headers: { "content-type": "application/json" }
                    });
                  }
                }
              `,
            },
          ],
        },
      },
    },
  },
});
```

The `workers` array registers in-memory Workers by name. Miniflare resolves the `AUTH` and `PRICING` bindings to these instead of making network calls.

---

## 2. The Gateway Worker Under Test

```typescript
// src/gateway.ts
export interface Env {
  AUTH: Fetcher;
  PRICING: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Authenticate
    const authRes = await env.AUTH.fetch(
      new Request("https://auth.internal/verify", {
        method: "POST",
        headers: { authorization: request.headers.get("authorization") ?? "" },
      })
    );

    if (!authRes.ok) {
      return new Response("Unauthorized", { status: 401 });
    }

    const { userId } = await authRes.json<{ userId: string }>();

    // 2. Get price
    const pricingRes = await env.PRICING.fetch(
      new Request(`https://pricing.internal/price?userId=${userId}`)
    );

    if (!pricingRes.ok) {
      return new Response("Pricing unavailable", { status: 502 });
    }

    const { price } = await pricingRes.json<{ price: number }>();

    return Response.json({ userId, price });
  },
};
```

---

## 3. Integration Tests Using Local Stub Workers

When `vitest-pool-workers` resolves service bindings to the in-memory stubs defined in `vitest.config.ts`, the test exercises the full gateway code path:

```typescript
// src/__tests__/gateway.integration.test.ts
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import worker from "../gateway";
import { describe, it, expect } from "vitest";

async function callGateway(authHeader = "Bearer valid-token") {
  const ctx = createExecutionContext();
  const res = await worker.fetch(
    new Request("https://gateway.example.com/checkout", {
      headers: { authorization: authHeader },
    }),
    env,
    ctx
  );
  await waitOnExecutionContext(ctx);
  return res;
}

describe("gateway integration (stub workers)", () => {
  it("returns userId and price for a valid token", async () => {
    const res = await callGateway();
    expect(res.status).toBe(200);
    const body = await res.json<{ userId: string; price: number }>();
    expect(body.userId).toBe("u_test");
    expect(body.price).toBe(9.99);
  });
});
```

This catches integration issues — wrong JSON shape, missing headers, URL construction errors — without needing deployed Workers.

---

## 4. Unit Tests with a Hand-rolled `Fetcher` Stub

For testing specific error branches, inject a custom `Fetcher` directly into `env`. This bypasses the Miniflare worker wiring entirely and gives you per-test control:

```typescript
// src/__tests__/gateway.unit.test.ts
import { createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import worker, { type Env } from "../gateway";
import { describe, it, expect, vi } from "vitest";

function makeFetcher(response: Response): Fetcher {
  return {
    fetch: vi.fn().mockResolvedValue(response),
  } as unknown as Fetcher;
}

function makeEnv(overrides: Partial<Env>): Env {
  return {
    AUTH: makeFetcher(Response.json({ userId: "u_default" })),
    PRICING: makeFetcher(Response.json({ price: 0 })),
    ...overrides,
  };
}

async function callWith(env: Env, authHeader = "Bearer tok") {
  const ctx = createExecutionContext();
  const res = await worker.fetch(
    new Request("https://gw.example.com/checkout", {
      headers: { authorization: authHeader },
    }),
    env,
    ctx
  );
  await waitOnExecutionContext(ctx);
  return res;
}

describe("gateway unit — auth failures", () => {
  it("returns 401 when auth Worker returns 401", async () => {
    const env = makeEnv({ AUTH: makeFetcher(new Response("Unauthorized", { status: 401 })) });
    const res = await callWith(env);
    expect(res.status).toBe(401);
  });

  it("returns 401 when auth Worker returns 403", async () => {
    const env = makeEnv({ AUTH: makeFetcher(new Response("Forbidden", { status: 403 })) });
    const res = await callWith(env);
    expect(res.status).toBe(401);
  });
});

describe("gateway unit — pricing failures", () => {
  it("returns 502 when pricing Worker is unavailable", async () => {
    const env = makeEnv({
      PRICING: makeFetcher(new Response("Service unavailable", { status: 503 })),
    });
    const res = await callWith(env);
    expect(res.status).toBe(502);
  });
});

describe("gateway unit — header forwarding", () => {
  it("forwards authorization header to auth Worker", async () => {
    const authFetcher = makeFetcher(Response.json({ userId: "u_check" }));
    const env = makeEnv({ AUTH: authFetcher });
    await callWith(env, "Bearer my-secret");

    const calledWith = (authFetcher.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as Request;
    expect(calledWith.headers.get("authorization")).toBe("Bearer my-secret");
  });

  it("passes correct userId to pricing Worker", async () => {
    const pricingFetcher = makeFetcher(Response.json({ price: 5 }));
    const env = makeEnv({ PRICING: pricingFetcher });
    await callWith(env);

    const calledWith = (pricingFetcher.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as Request;
    expect(new URL(calledWith.url).searchParams.get("userId")).toBe("u_default");
  });
});
```

---

## 5. Testing RPC-style Service Bindings (Workers RPC)

Workers RPC lets you call methods on another Worker as if it were a class instance. Test this with a typed stub that satisfies the same interface:

```typescript
// src/rpc-types.ts — shared between Workers
export interface PricingRPC extends Rpc.WorkerEntrypoint {
  getPrice(userId: string): Promise<number>;
}
```

```typescript
// src/gateway-rpc.ts
export interface Env {
  PRICING: Service<PricingRPC>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const userId = url.searchParams.get("userId") ?? "anonymous";
    const price = await env.PRICING.getPrice(userId);
    return Response.json({ userId, price });
  },
};
```

```typescript
// src/__tests__/gateway-rpc.test.ts
import { createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import worker from "../gateway-rpc";
import { type Env } from "../gateway-rpc";
import { describe, it, expect, vi } from "vitest";

function makeRpcEnv(price: number): Env {
  return {
    PRICING: {
      getPrice: vi.fn().mockResolvedValue(price),
    } as unknown as Service<import("../rpc-types").PricingRPC>,
  };
}

describe("gateway RPC", () => {
  it("returns the price from the RPC stub", async () => {
    const env = makeRpcEnv(19.99);
    const ctx = createExecutionContext();
    const res = await worker.fetch(
      new Request("https://gw.example.com/?userId=u_abc"),
      env,
      ctx
    );
    await waitOnExecutionContext(ctx);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ userId: "u_abc", price: 19.99 });
  });

  it("invokes getPrice with the correct userId", async () => {
    const env = makeRpcEnv(0);
    const ctx = createExecutionContext();
    await worker.fetch(new Request("https://gw.example.com/?userId=u_xyz"), env, ctx);
    await waitOnExecutionContext(ctx);
    expect(env.PRICING.getPrice).toHaveBeenCalledWith("u_xyz");
  });
});
```

---

## 6. End-to-end Test: Two Real Local Workers

When you need true end-to-end coverage — both the gateway and a real downstream implementation — define both Workers' modules in Miniflare rather than using inline scripts:

```typescript
// vitest.config.e2e.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    include: ["src/__tests__/*.e2e.test.ts"],
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          workers: [
            {
              name: "auth-worker",
              modules: true,
              // Reference the actual built auth worker source
              scriptPath: "./dist/auth-worker.js",
            },
          ],
        },
      },
    },
  },
});
```

This wires the real auth Worker source rather than a stub, catching behavioural regressions across the boundary.

---

## Anti-patterns

- **Mocking `fetch` globally with `vi.mock` for service bindings.** Service binding calls go through `env.BINDING.fetch(...)`, not the global `fetch`. Patching the global has no effect and gives false confidence.
- **Asserting the URL the stub was called with as a string comparison.** Service binding internal URLs (`https://auth.internal/...`) are an implementation detail. Test the *observable effects* (response status, returned JSON) rather than internal routing URLs where possible.
- **Using a single stub for all tests without resetting call counts.** `vi.fn()` accumulates call history across tests in the same file. Add `vi.clearAllMocks()` (or use `clearMocks: true` in vitest config) in `beforeEach`.
- **Treating local Worker wiring as equivalent to production.** Miniflare runs Workers in the same process. Latency, serialisation, and error propagation differ from real cross-Worker calls. Integration tests using stub Workers catch logic bugs but not network-level issues.
- **Skipping type assertions on the stub `Fetcher`.** `as unknown as Fetcher` is a red flag — keep it minimal and document it. If the gateway uses methods beyond `fetch`, the stub will silently fail at runtime in production.

---

## Gotchas

- Service binding stubs in `vitest.config.ts` `workers` arrays use `name:` that must exactly match the `service:` field in `wrangler.toml`, not the `binding:` name. The binding name is the key in `env`; the service name is the worker's identity.
- `createExecutionContext()` must be called *inside* each test, not once at the module level. The context is single-use; reusing it across tests or across requests within a test causes unresolved-promise errors.
- When the downstream stub Worker returns a `Response` whose `body` is a `ReadableStream`, and the gateway reads it with `.json()`, the stream is consumed. If the stub returns a `Response` constructed with `Response.json(...)`, a second `.json()` call on the same object throws. Build fresh `Response` objects per test or per `vi.fn()` call.
- Miniflare's in-memory Workers share the V8 isolate with the gateway Worker. Real service bindings cross isolate boundaries. This means shared global state (module-level singletons, caches) that would be isolated in production might bleed across the boundary in Miniflare tests. Keep downstream stub Workers stateless.
- `waitOnExecutionContext(ctx)` is required whenever the gateway Worker uses `ctx.waitUntil(...)`. Omitting it lets background tasks run after the test ends and can cause confusing assertion failures in subsequent tests.

---

## Verification

```bash
# Unit tests only
npx vitest run src/__tests__/gateway.unit.test.ts

# Integration tests with stub workers
npx vitest run src/__tests__/gateway.integration.test.ts

# All tests, verbose
npx vitest run --reporter=verbose

# Coverage report
npx vitest run --coverage
```

Expected output:

```
✓ src/__tests__/gateway.unit.test.ts (7 tests) 89ms
  ✓ gateway unit — auth failures (2)
  ✓ gateway unit — pricing failures (1)
  ✓ gateway unit — header forwarding (2)
  ✓ gateway RPC (2)
✓ src/__tests__/gateway.integration.test.ts (1 test) 204ms
  ✓ gateway integration (stub workers) (1)
```

---

## Related

- `vitest-cloudflare-pool-workers.md` — pool-workers configuration, `isolatedStorage`, env helper
- `workers-test-patterns.md` — broader patterns for testing Workers handlers
- `test-doubles-cloudflare-workers.md` — stubs, spies, and fakes taxonomy for Workers bindings
- `chaos-engineering-cloudflare-workers.md` — injecting faults into service binding calls
- `durable-objects-miniflare-fake-timers.md` — DO binding stubs alongside service bindings

---

## Sources

- Cloudflare Service Bindings docs: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Workers RPC guide: https://developers.cloudflare.com/workers/runtime-apis/rpc/
- `@cloudflare/vitest-pool-workers` configuration: https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- Miniflare multi-worker wiring: https://miniflare.dev/get-started/core-concepts#multiple-workers
- Cloudflare blog — Testing Service Bindings locally: https://blog.cloudflare.com/miniflare/
