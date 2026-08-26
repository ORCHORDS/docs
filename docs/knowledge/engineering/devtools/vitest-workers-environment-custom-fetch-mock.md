# Vitest Workers Environment Custom Fetch Mock

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Worker calls external APIs with `fetch()`. In unit tests you want deterministic responses
without hitting real endpoints, but the standard `vi.fn()` / `globalThis.fetch = ...` approach
breaks under `@cloudflare/vitest-pool-workers` because the Workers runtime owns the global
`fetch` binding and does not allow naive reassignment via `vi.spyOn`. You need an approach that
works inside the Workers sandbox while keeping tests isolated and resettable.

## Context

`@cloudflare/vitest-pool-workers` runs each test file inside a real Miniflare (V8 isolate)
environment. The global `fetch` in that context is a native Workers fetch, not the Node.js one.
`vi.spyOn(globalThis, "fetch")` works syntactically but the intercepted calls may still escape
to the network if the binding is not properly plumbed.

The recommended pattern uses a `fetchMock` helper that wraps the `undici` `MockAgent` interface
exposed through Miniflare, or an explicit service binding mock, depending on whether the fetch
target is an external URL or another Worker.

## 1. Install and Configure the Fetch Mock Pool

```bash
npm install --save-dev @cloudflare/vitest-pool-workers
# no extra dependencies needed — the mock API is part of cloudflare:test
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        // Allow outbound fetch to be intercepted in tests
        fetchMock: {
          // Intercept all outbound fetch by default; un-matched requests throw
          // rather than making real network calls — prevents test bleed.
          passThrough: false,
        },
      },
    },
  },
});
```

## 2. Using `fetchMock` from `cloudflare:test`

```typescript
// src/weather.spec.ts
import { fetchMock } from "cloudflare:test";
import { describe, it, expect, beforeAll, afterEach } from "vitest";
import { handleRequest } from "./weather";

// Activate fetch mocking at the module level for this test file.
beforeAll(() => {
  fetchMock.activate();
  fetchMock.disableNetConnect();
});

afterEach(() => {
  // Assert no pending, unused mocks remain — catches test ordering bugs.
  fetchMock.assertNoPendingInterceptors();
});

describe("handleRequest: weather endpoint", () => {
  it("returns formatted temperature when API responds 200", async () => {
    fetchMock
      .get("https://api.weather.example.com")
      .intercept({ path: "/v1/current?city=London" })
      .reply(200, { temp_c: 18.5, condition: "Cloudy" }, {
        headers: { "Content-Type": "application/json" },
      });

    const request = new Request("https://worker.test/weather?city=London");
    const env = {} as Env; // bindings not needed for this unit test
    const response = await handleRequest(request, env);

    expect(response.status).toBe(200);
    const body = await response.json<{ temperature: string }>();
    expect(body.temperature).toBe("18.5°C");
  });

  it("propagates upstream 503 as 502 Bad Gateway", async () => {
    fetchMock
      .get("https://api.weather.example.com")
      .intercept({ path: "/v1/current?city=London" })
      .reply(503, "Service Unavailable");

    const request = new Request("https://worker.test/weather?city=London");
    const response = await handleRequest(request, {} as Env);

    expect(response.status).toBe(502);
  });
});
```

## 3. Worker Source Wired to `fetch()`

```typescript
// src/weather.ts
export async function handleRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const city = url.searchParams.get("city") ?? "London";

  const upstream = await fetch(
    `https://api.weather.example.com/v1/current?city=${encodeURIComponent(city)}`
  );

  if (!upstream.ok) {
    return new Response("Upstream error", { status: 502 });
  }

  const data = await upstream.json<{ temp_c: number; condition: string }>();
  return Response.json({ temperature: `${data.temp_c}°C`, condition: data.condition });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return handleRequest(request, env);
  },
} satisfies ExportedHandler<Env>;
```

## 4. Resetting Mocks Between Tests

```typescript
// src/auth.spec.ts
import { fetchMock } from "cloudflare:test";
import { beforeAll, afterEach, afterAll, it, expect } from "vitest";

beforeAll(() => {
  fetchMock.activate();
  fetchMock.disableNetConnect();
});

// Reset all interceptors after every test to prevent cross-test contamination.
afterEach(() => {
  fetchMock.resetHandlers();
});

afterAll(() => {
  // Restore native fetch so other test files are not affected.
  fetchMock.deactivate();
});

it("handles auth token refresh", async () => {
  fetchMock
    .get("https://auth.example.com")
    .intercept({ path: "/token", method: "POST" })
    .reply(200, { access_token: "tok_abc123", expires_in: 3600 });

  const response = await fetch("https://auth.example.com/token", {
    method: "POST",
    body: new URLSearchParams({ grant_type: "client_credentials" }),
  });

  expect(response.status).toBe(200);
  const { access_token } = await response.json<{ access_token: string }>();
  expect(access_token).toBe("tok_abc123");
});
```

## 5. Mocking Fetch Inside Service Binding Calls

When the Worker delegates to another Worker via a service binding, mock the binding's `fetch`
instead of the outbound URL:

```typescript
// vitest.config.ts  (service binding mock)
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        // Provide a mock implementation for the AUTH_SERVICE binding.
        miniflare: {
          serviceBindings: {
            AUTH_SERVICE: async (request: Request) => {
              if (request.url.endsWith("/verify")) {
                return Response.json({ valid: true });
              }
              return new Response("Not Found", { status: 404 });
            },
          },
        },
      },
    },
  },
});
```

```typescript
// src/protected.spec.ts
import { env } from "cloudflare:test";
import { it, expect } from "vitest";
import worker from "./index";

it("passes through when AUTH_SERVICE confirms valid token", async () => {
  const request = new Request("https://worker.test/protected", {
    headers: { Authorization: "Bearer valid-token" },
  });
  // env.AUTH_SERVICE is the mock defined in vitest.config.ts
  const response = await worker.fetch(request, env);
  expect(response.status).toBe(200);
});
```

## 6. Asserting Request Details in the Mock

```typescript
import { fetchMock } from "cloudflare:test";
import { it, expect, beforeAll, afterEach } from "vitest";

beforeAll(() => { fetchMock.activate(); fetchMock.disableNetConnect(); });
afterEach(() => { fetchMock.assertNoPendingInterceptors(); });

it("sends Authorization header to upstream", async () => {
  let capturedHeaders: Record<string, string> = {};

  fetchMock
    .get("https://payments.example.com")
    .intercept({ path: "/charge" })
    .reply(function (this: { req: { headers: Record<string, string> } }) {
      capturedHeaders = this.req.headers;
      return { statusCode: 200, data: JSON.stringify({ charged: true }) };
    });

  await fetch("https://payments.example.com/charge", {
    headers: { Authorization: "Bearer sk_test_123" },
  });

  expect(capturedHeaders["authorization"]).toBe("Bearer sk_test_123");
});
```

## Anti-patterns

- **`globalThis.fetch = vi.fn()`** — works in Node environments but is inert or throws in the
  Miniflare isolate; use `fetchMock` from `cloudflare:test` instead.
- **Leaving `fetchMock.activate()` in place across test files** — if one file forgets to call
  `fetchMock.deactivate()` in `afterAll`, the next file's real fetches are silently blocked.
- **Skipping `assertNoPendingInterceptors()`** — unused interceptors silently accumulate and mask
  logic branches that were never exercised.
- **Mocking the URL in `miniflare.serviceBindings` and in `fetchMock` simultaneously** — double
  mocking leads to precedence confusion; pick one mechanism per dependency.

## Gotchas

- `fetchMock` from `cloudflare:test` is only available inside the Workers pool; importing it in
  a `node` environment vitest project throws at import time.
- Interceptors are matched in registration order; register more-specific paths before wildcards.
- Miniflare's fetch mock is not the same as `msw` — it does not support service workers or
  browser-side interception. For E2E tests use Playwright's route interception instead.
- `passThrough: false` in `vitest.config.ts` affects all test files in the pool; set
  `fetchMock.enableNetConnect("localhost")` in individual files that need real local calls.

## Verification

```bash
# Run with verbose output to see interceptor matches
npx vitest run --reporter=verbose src/weather.spec.ts

# Confirm no real outbound requests escape in CI (will print network errors if mocks are wrong)
MINIFLARE_LOG=debug npx vitest run 2>&1 | grep -i "fetch\|intercept"
```

## Related

- `vitest-workers-miniflare-testing-setup.md`
- `msw-external-api-mocking-workers-tests.md`
- `vitest-workers-module-mock-inject.md`
- `miniflare-custom-plugins-bindings.md`
- `wrangler-service-bindings-multi-worker-local-dev.md`

## Sources

- https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/#fetchmock
- https://github.com/cloudflare/workers-sdk/blob/main/packages/vitest-pool-workers/README.md
- https://undici.nodejs.org/#/docs/api/MockAgent
- https://developers.cloudflare.com/workers/testing/vitest-integration/configuration/
