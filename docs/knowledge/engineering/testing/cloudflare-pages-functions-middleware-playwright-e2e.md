# Cloudflare Pages Functions Middleware Chain E2E Testing with Playwright

2026-08-24 / example.com / production

---

## Symptom / Use-case

Your Cloudflare Pages project uses `functions/_middleware.ts` for authentication and `functions/api/[[catchall]].ts` for API routing. The middleware chain — rate limiting, JWT validation, CORS, then the route handler — has never been exercised end-to-end in a real browser context. Unit tests cover each middleware in isolation but miss the interaction effects: a middleware that sets a response header before passing to `next()` is accidentally overwritten by the route handler, and only an E2E test with real header inspection catches it.

---

## Context

Cloudflare Pages Functions execute in a specific middleware chain order determined by the file system layout under `functions/`. The chain is:

1. `functions/_middleware.ts` — root middleware (global to all routes)
2. `functions/api/_middleware.ts` — namespace middleware (applies to `/api/*`)
3. `functions/api/items.ts` — specific route handler

`wrangler pages dev` runs this chain locally, exposing a real HTTP server. Playwright's `webServer` option starts `wrangler pages dev` before the test suite, and tests make real browser and API requests through the full middleware stack.

This article focuses on testing middleware chain behaviour — header propagation, authentication short-circuits, CORS preflight handling — rather than general Pages E2E patterns already covered in `playwright-cloudflare-pages-e2e.md`.

---

## Project Structure

```
my-pages-app/
  functions/
    _middleware.ts          ← rate limit + request-id injection
    api/
      _middleware.ts        ← JWT auth guard
      items.ts              ← route: GET /api/items
  playwright.config.ts
  test/
    e2e/
      middleware-chain.spec.ts
      auth-guard.spec.ts
      cors.spec.ts
```

---

## Playwright Configuration for Pages Dev

```ts
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./test/e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:8788",
  },
  webServer: {
    command: "npx wrangler pages dev . --port 8788 --compatibility-date 2025-01-01",
    url: "http://localhost:8788",
    reuseExistingServer: !process.env.CI,
    stdout: "pipe",
    stderr: "pipe",
    // Wait until the dev server is ready
    timeout: 60_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
```

---

## Root Middleware: Request-ID Injection Test

```ts
// functions/_middleware.ts (production code under test)
import type { PagesFunction } from "@cloudflare/workers-types";

export const onRequest: PagesFunction = async (ctx) => {
  const requestId = crypto.randomUUID();
  ctx.request.headers.set("X-Request-ID", requestId); // injected for downstream
  const response = await ctx.next();
  response.headers.set("X-Request-ID", requestId);    // echoed in response
  return response;
};
```

```ts
// test/e2e/middleware-chain.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Root middleware — request ID propagation", () => {
  test("every response carries a valid X-Request-ID header", async ({ request }) => {
    const res = await request.get("/api/items");
    const requestId = res.headers()["x-request-id"];

    expect(requestId).toBeDefined();
    expect(requestId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );
  });

  test("X-Request-ID is stable within a single response (not changed by downstream middleware)", async ({
    request,
  }) => {
    // Hit an auth-guarded route that returns 401; root middleware still runs
    const res = await request.get("/api/items", {
      headers: { Authorization: "" }, // deliberately missing token
    });
    const requestId = res.headers()["x-request-id"];
    expect(requestId).toBeDefined();
    // Confirm it is a single UUID, not two concatenated values
    expect(requestId!.split(",")).toHaveLength(1);
  });
});
```

---

## Auth Middleware: Short-Circuit Behaviour

```ts
// functions/api/_middleware.ts (production code)
import type { PagesFunction } from "@cloudflare/workers-types";

export const onRequest: PagesFunction<Env> = async (ctx) => {
  const auth = ctx.request.headers.get("Authorization") ?? "";
  const [, token] = auth.split(" ");

  if (!token || token !== ctx.env.API_SECRET) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  return ctx.next();
};
```

```ts
// test/e2e/auth-guard.spec.ts
import { test, expect } from "@playwright/test";

const VALID_TOKEN = process.env.TEST_API_SECRET ?? "test-secret";

test.describe("API middleware — JWT auth guard", () => {
  test("returns 401 with no Authorization header", async ({ request }) => {
    const res = await request.get("/api/items");
    expect(res.status()).toBe(401);
    const body = await res.json();
    expect(body).toMatchObject({ error: "Unauthorized" });
  });

  test("returns 401 with a malformed Bearer token", async ({ request }) => {
    const res = await request.get("/api/items", {
      headers: { Authorization: "NotBearer abc" },
    });
    expect(res.status()).toBe(401);
  });

  test("passes through to the route handler with a valid token", async ({ request }) => {
    const res = await request.get("/api/items", {
      headers: { Authorization: `Bearer ${VALID_TOKEN}` },
    });
    expect(res.status()).toBe(200);
  });

  test("401 response still carries the root middleware X-Request-ID", async ({ request }) => {
    // Validates that the auth middleware short-circuit does not swallow root headers
    const res = await request.get("/api/items");
    expect(res.status()).toBe(401);
    expect(res.headers()["x-request-id"]).toMatch(
      /^[0-9a-f-]{36}$/i,
    );
  });
});
```

---

## CORS Preflight Middleware Chain Test

```ts
// test/e2e/cors.spec.ts
import { test, expect } from "@playwright/test";

const VALID_TOKEN = process.env.TEST_API_SECRET ?? "test-secret";

test.describe("CORS preflight — OPTIONS short-circuit", () => {
  test("OPTIONS /api/items returns 204 with correct CORS headers", async ({ request }) => {
    const res = await request.fetch("/api/items", {
      method: "OPTIONS",
      headers: {
        Origin: "https://app.example.com",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
      },
    });

    expect(res.status()).toBe(204);
    expect(res.headers()["access-control-allow-origin"]).toBe(
      "https://app.example.com",
    );
    expect(res.headers()["access-control-allow-methods"]).toContain("GET");
    expect(res.headers()["access-control-allow-headers"]).toContain(
      "Authorization",
    );
  });

  test("authenticated request carries CORS allow-origin on the real response", async ({
    request,
  }) => {
    const res = await request.get("/api/items", {
      headers: {
        Authorization: `Bearer ${VALID_TOKEN}`,
        Origin: "https://app.example.com",
      },
    });
    expect(res.headers()["access-control-allow-origin"]).toBe(
      "https://app.example.com",
    );
  });
});
```

---

## Browser Test: Middleware Header Visible to `fetch()`

```ts
// test/e2e/browser-middleware-headers.spec.ts
import { test, expect } from "@playwright/test";

test("browser fetch sees X-Request-ID from middleware", async ({ page }) => {
  const VALID_TOKEN = process.env.TEST_API_SECRET ?? "test-secret";

  // Navigate to the app shell
  await page.goto("/");

  // Make a fetch from within the browser page context
  const requestId = await page.evaluate(async (token) => {
    const res = await fetch("/api/items", {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.headers.get("x-request-id");
  }, VALID_TOKEN);

  expect(requestId).toMatch(/^[0-9a-f-]{36}$/i);
});
```

---

## Wrangler Secrets for E2E

Store test secrets in `.dev.vars` so `wrangler pages dev` injects them as environment variables:

```ini
# .dev.vars (gitignored)
API_SECRET=test-secret
```

In CI, pass them as environment variables:

```yaml
# .github/workflows/e2e.yml
- name: Run Playwright E2E tests
  env:
    TEST_API_SECRET: ${{ secrets.TEST_API_SECRET }}
    CLOUDFLARE_PAGES_DEV_SECRETS: "API_SECRET=${{ secrets.TEST_API_SECRET }}"
  run: npx playwright test
```

---

## Anti-patterns

- **Mocking middleware in E2E tests** — the point of E2E middleware tests is the real chain executing; do not intercept `wrangler pages dev` traffic with Playwright's `page.route()` unless testing specific network failure scenarios.
- **Testing only the happy path** — the most valuable middleware tests are the short-circuits (401, 429, 405); ensure every `ctx.next()` branch and every early-return branch is exercised.
- **Hardcoding the dev server port in tests** — use `baseURL` from `playwright.config.ts`; individual tests should use relative paths.
- **Using `page.goto()` for API-only tests** — use `request.get/post()` from Playwright's API request context for JSON API endpoints; it's faster and doesn't render a page.
- **Ignoring root middleware on error responses** — verify that auth 401s and 429s still carry headers injected by the root middleware; this is a common source of middleware chain bugs.

---

## Gotchas

- `wrangler pages dev` does not hot-reload middleware changes by default in some versions; use the `--live-reload` flag or restart between test runs when iterating on middleware code.
- Playwright's `request` fixture uses a separate HTTP client from the `page` fixture; cookies set in the browser `page` are not automatically sent in `request.get()` calls.
- The `.dev.vars` file must exist before `wrangler pages dev` starts — the `webServer.command` in `playwright.config.ts` does not wait for secrets to be injected.
- `wrangler pages dev` binds KV, D1, and R2 via `--kv`, `--d1`, and `--r2` flags or `wrangler.toml`; ensure these are configured for the E2E environment with test-specific binding names to avoid contaminating production namespaces.
- `ctx.request.headers.set()` on the incoming `Request` is not directly supported in the Workers standard: `Request` objects are immutable. Use `new Request(ctx.request, { headers: mergedHeaders })` and replace `ctx.request` on a custom context property.

---

## Verification

```bash
# Install Playwright browsers once
npx playwright install chromium

# Run the middleware E2E suite against the local dev server
npx playwright test test/e2e/middleware-chain.spec.ts --reporter=list

# Run all E2E tests with full trace on failure
npx playwright test --trace=on-first-retry

# Open the trace viewer if tests fail
npx playwright show-trace test-results/*/trace.zip
```

Expected: all middleware chain specs pass; trace shows the `X-Request-ID` header present in every response including 401s.

---

## Related

- `playwright-cloudflare-pages-e2e.md` — general Pages E2E setup and patterns
- `playwright-workers-auth-flow-session-persistence-e2e.md` — session auth E2E patterns
- `playwright-workers-rate-limiting-integration-testing.md` — rate limit middleware E2E
- `playwright-network-interception.md` — when to mock network in E2E
- `playwright-fixtures.md` — Playwright fixture sharing for auth tokens

---

## Sources

- Cloudflare Pages Functions middleware: https://developers.cloudflare.com/pages/functions/middleware/
- Pages Functions routing: https://developers.cloudflare.com/pages/functions/routing/
- Playwright `webServer` option: https://playwright.dev/docs/test-webserver
- Wrangler Pages dev: https://developers.cloudflare.com/workers/wrangler/commands/#dev-1
- Pages `.dev.vars`: https://developers.cloudflare.com/pages/functions/bindings/#interact-with-your-pages-functions-locally
