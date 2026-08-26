# Mocking External Fetch Calls in Workers Tests with MSW

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your Cloudflare Worker calls third-party APIs (Stripe, Resend, a partner REST service) and you need deterministic unit tests that don't make real network requests, without manually patching the global `fetch`.

## Context
Mock Service Worker (MSW) v2 ships a `@mswjs/interceptors` layer that works in Node.js processes and can intercept `fetch` calls made during Vitest runs. When combined with `@cloudflare/vitest-pool-workers`, MSW handlers run in the Node.js side (the host) while the Worker code runs in workerd — requiring a small bridge. For workers running in standard Vitest (non-pool), MSW's `setupServer` from `msw/node` intercepts outbound fetches transparently.

## Installation

```bash
pnpm add -D msw
# MSW v2 requires no additional polyfill for Node 18+
```

## Standard Vitest Setup (non-pool)

For Workers code that can run in a standard Node.js Vitest environment (using `wrangler-env` stubs or Miniflare directly):

```typescript
// test/msw-server.ts
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

// Define reusable default handlers
export const handlers = [
  http.get("https://api.stripe.com/v1/customers/:id", ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      email: "test@example.com",
      object: "customer",
    });
  }),

  http.post("https://api.resend.com/emails", async ({ request }) => {
    const body = await request.json() as { to: string };
    if (!body.to) {
      return new HttpResponse("Missing 'to' field", { status: 400 });
    }
    return HttpResponse.json({ id: "email_abc123" }, { status: 200 });
  }),

  // Catch-all: fail any unmocked outbound request explicitly
  http.all("*", ({ request }) => {
    console.error(`[MSW] Unmocked request: ${request.method} ${request.url}`);
    return new HttpResponse("Not mocked", { status: 500 });
  }),
];

export const server = setupServer(...handlers);
```

```typescript
// vitest.setup.ts
import { server } from "./test/msw-server";
import { beforeAll, afterEach, afterAll } from "vitest";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());  // Remove per-test overrides
afterAll(() => server.close());
```

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    setupFiles: ["./vitest.setup.ts"],
    environment: "node",
  },
});
```

## Writing Tests with Handler Overrides

Override handlers per test to simulate error paths or different responses:

```typescript
// src/stripe.test.ts
import { http, HttpResponse } from "msw";
import { server } from "../test/msw-server";
import { createStripeCustomer, getStripeCustomer } from "./stripe";
import { describe, it, expect } from "vitest";

const mockEnv = {
  STRIPE_SECRET_KEY: "sk_test_abc",
} as unknown as Env;

describe("getStripeCustomer", () => {
  it("returns customer data on success", async () => {
    const customer = await getStripeCustomer(mockEnv, "cus_123");
    expect(customer.email).toBe("test@example.com");
  });

  it("throws when Stripe returns 404", async () => {
    server.use(
      http.get("https://api.stripe.com/v1/customers/:id", () =>
        HttpResponse.json(
          { error: { message: "No such customer" } },
          { status: 404 }
        )
      )
    );

    await expect(getStripeCustomer(mockEnv, "cus_missing")).rejects.toThrow(
      "No such customer"
    );
  });

  it("retries on 429 and succeeds on second attempt", async () => {
    let callCount = 0;
    server.use(
      http.get("https://api.stripe.com/v1/customers/:id", () => {
        callCount++;
        if (callCount === 1) {
          return new HttpResponse(null, {
            status: 429,
            headers: { "Retry-After": "0" },
          });
        }
        return HttpResponse.json({ id: "cus_123", email: "retry@example.com" });
      })
    );

    const customer = await getStripeCustomer(mockEnv, "cus_123");
    expect(callCount).toBe(2);
    expect(customer.email).toBe("retry@example.com");
  });
});
```

## Simulating Network-Level Failures

MSW can simulate connection errors (timeouts, DNS failures) using `HttpResponse.error()`:

```typescript
// src/email.test.ts
import { http, HttpResponse } from "msw";
import { server } from "../test/msw-server";
import { sendWelcomeEmail } from "./email";
import { it, expect } from "vitest";

it("handles network failure from Resend gracefully", async () => {
  server.use(
    http.post("https://api.resend.com/emails", () =>
      HttpResponse.error()  // Simulates a connection reset / network drop
    )
  );

  const result = await sendWelcomeEmail({ to: "user@example.com", name: "Alice" });
  // Worker should catch the fetch error and return a degraded result
  expect(result.sent).toBe(false);
  expect(result.error).toMatch(/network/i);
});
```

## Scoped Handlers Per Test Suite

For large test files, use `server.boundary()` (MSW v2.4+) to scope handlers to a describe block:

```typescript
// src/payments.test.ts
import { http, HttpResponse } from "msw";
import { server } from "../test/msw-server";
import { describe, it, expect } from "vitest";
import { processPayment } from "./payments";

describe("processPayment", () => {
  // These handlers are isolated to this describe block
  const boundary = server.boundary(() => {
    server.use(
      http.post("https://api.stripe.com/v1/payment_intents", () =>
        HttpResponse.json({ id: "pi_test", status: "succeeded" })
      )
    );
  });

  boundary.listen();

  it("marks order as paid on succeeded intent", async () => {
    const result = await processPayment({ amount: 1000, currency: "usd" });
    expect(result.status).toBe("paid");
  });

  boundary.close();
});
```

## Anti-patterns
- Calling `vi.stubGlobal("fetch", mockFn)` per test; this is fragile, bypasses request matching, and doesn't restore automatically on failure.
- Using `onUnhandledRequest: "warn"` instead of `"error"` in CI; silent pass-throughs let real network calls slip in and make tests environment-dependent.
- Defining handlers inside test bodies without `server.use()` — they won't be registered.
- Forgetting `server.resetHandlers()` in `afterEach`; per-test overrides bleed into subsequent tests.
- Mocking at the module level with `vi.mock("./stripe")` when the goal is to test the actual fetch logic; prefer MSW to exercise the real implementation.

## Gotchas
- MSW v2 drops the `rest` namespace; use `http` from `"msw"` for all REST handlers.
- `HttpResponse.error()` throws a `TypeError: Failed to fetch` in the caller, not an HTTP error response — handle it differently than non-2xx responses.
- When using `@cloudflare/vitest-pool-workers`, outbound fetch from workerd bypasses Node.js interceptors; you must use the `fetchMock` binding option in `miniflare` pool config instead of MSW.
- `server.listen()` must be called before any test imports that trigger side-effectful fetches (e.g. module-level SDK initialization).
- MSW does not intercept `undici` or `node:http` by default; only global `fetch` is intercepted without additional `@mswjs/interceptors` configuration.

## Verification
```bash
pnpm vitest run src/stripe.test.ts --reporter=verbose
# Confirm no real network calls: run with NODE_OPTIONS='--dns-result-order=ipv4first' and check for 500 from catch-all
```

## Related
- `/documentation/categories/devtools/vitest-pool-workers-cloudflare-test-api.md`
- `/documentation/categories/devtools/hono-test-utils-workers-unit-testing.md`
- `/documentation/categories/devtools/vitest-workers-miniflare-testing-setup.md`

## Sources
- https://mswjs.io/docs/getting-started
- https://mswjs.io/docs/api/setup-server
- https://mswjs.io/docs/api/http
