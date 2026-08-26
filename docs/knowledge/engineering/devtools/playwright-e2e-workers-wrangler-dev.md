# Playwright E2E Testing Against Wrangler Dev Server

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You want full end-to-end tests for a Cloudflare Workers API or Workers-powered frontend that run against the real `wrangler dev` server in CI, catching routing, middleware, and binding issues that unit tests miss.

## Context
Playwright's `webServer` option can start and await `wrangler dev` before the test suite begins, giving tests a real Workers runtime at `localhost`. This approach tests the full request/response cycle including Hono routing, auth middleware, D1 queries, and KV reads. Unlike `@cloudflare/vitest-pool-workers`, Playwright tests are written from the outside — they make HTTP requests (or drive a browser) and assert on observable behavior.

## Project Structure

```
project/
├── src/
│   └── index.ts          # Worker entrypoint
├── wrangler.toml
├── playwright.config.ts
├── e2e/
│   ├── api.spec.ts
│   └── auth.spec.ts
└── package.json
```

```bash
pnpm add -D @playwright/test
pnpm exec playwright install chromium --with-deps
```

## playwright.config.ts Setup

Point `webServer` at `wrangler dev` and set `baseURL` so tests can use relative paths:

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

const PORT = 8788;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: `http://localhost:${PORT}`,
    // Use fetch-based requests for API tests (no browser launch overhead)
    extraHTTPHeaders: {
      Accept: "application/json",
    },
  },

  webServer: {
    // --local keeps all bindings in-process; --port pins the port
    command: `pnpm wrangler dev --local --port ${PORT} --env test`,
    url: `http://localhost:${PORT}/healthz`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },

  projects: [
    {
      name: "api",
      // API-only tests don't need a real browser
      use: { ...devices["Desktop Chrome"], browserName: "chromium" },
    },
  ],
});
```

## Writing API Tests with request Fixture

Use the Playwright `request` fixture for headless HTTP testing — no browser, no DOM:

```typescript
// e2e/api.spec.ts
import { test, expect } from "@playwright/test";

test.describe("GET /items", () => {
  test("returns empty array when no items exist", async ({ request }) => {
    const response = await request.get("/items");

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toEqual({ items: [], total: 0 });
  });

  test("returns 401 without Authorization header", async ({ request }) => {
    const response = await request.get("/items/secret");
    expect(response.status()).toBe(401);
  });
});

test.describe("POST /items", () => {
  test("creates an item and returns 201 with Location header", async ({ request }) => {
    const response = await request.post("/items", {
      data: { name: "widget", price: 9.99 },
    });

    expect(response.status()).toBe(201);
    expect(response.headers()["location"]).toMatch(/^\/items\/[0-9a-f-]+$/);
  });

  test("rejects malformed JSON with 400", async ({ request }) => {
    const response = await request.post("/items", {
      headers: { "Content-Type": "application/json" },
      data: "not-json",
    });
    expect(response.status()).toBe(400);
  });
});
```

## Auth Flow Tests

Test cookie-based or token-based auth end-to-end:

```typescript
// e2e/auth.spec.ts
import { test, expect, APIRequestContext } from "@playwright/test";

async function signIn(request: APIRequestContext, email: string): Promise<string> {
  const res = await request.post("/auth/login", {
    data: { email, password: "test-password" },
  });
  expect(res.status()).toBe(200);
  const { token } = await res.json<{ token: string }>();
  return token;
}

test("authenticated requests succeed with Bearer token", async ({ request }) => {
  const token = await signIn(request, "alice@example.com");

  const profileRes = await request.get("/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(profileRes.status()).toBe(200);

  const profile = await profileRes.json<{ email: string }>();
  expect(profile.email).toBe("alice@example.com");
});

test("expired token returns 401 with WWW-Authenticate header", async ({ request }) => {
  const res = await request.get("/me", {
    headers: { Authorization: "Bearer expired.jwt.token" },
  });
  expect(res.status()).toBe(401);
  expect(res.headers()["www-authenticate"]).toContain("Bearer");
});
```

## Using Browser Tests for Workers-Rendered Pages

When the Worker serves HTML (e.g. via Workers + Assets or Hono SSR), add a browser project:

```typescript
// e2e/homepage.spec.ts
import { test, expect } from "@playwright/test";

test("homepage loads and shows navigation", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("nav")).toBeVisible();
  await expect(page.locator("h1")).toContainText("Welcome");
});

test("404 page renders with correct heading", async ({ page }) => {
  await page.goto("/this-does-not-exist");
  await expect(page.locator("h1")).toContainText("Not Found");
  // Verify the Worker returned a real 404 status
  const response = await page.request.get("/this-does-not-exist");
  expect(response.status()).toBe(404);
});
```

## CI GitHub Actions Integration

```yaml
# .github/workflows/e2e.yml
name: E2E Tests
on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with: { version: 9 }

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Install Playwright browsers
        run: pnpm exec playwright install chromium --with-deps

      - name: Run E2E tests
        run: pnpm exec playwright test
        env:
          CI: true
          # Provide secrets that wrangler.toml [env.test] bindings need
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Upload Playwright report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: playwright-report/
```

## Anti-patterns
- Relying on shared D1/KV state across tests without isolation; use per-test seed/teardown or separate named instances per test.
- Hardcoding `localhost:8787` instead of using `baseURL`; breaks when the port is already in use.
- Running `wrangler dev --remote` in CI; it hits live Cloudflare infrastructure and is slow, rate-limited, and non-deterministic.
- Skipping `reuseExistingServer: !process.env.CI`; in CI this should always be `false` to guarantee a fresh server state.
- Using the default `test` env that shares production binding names; define a `[env.test]` table in `wrangler.toml` with local-only bindings.

## Gotchas
- `wrangler dev` takes several seconds to start and hot-reload; set `webServer.timeout` to at least `60000` ms in CI.
- The `url` field in `webServer` must return a 2xx response before tests start; add a `/healthz` route that returns `200 OK`.
- Playwright's `request` fixture shares a cookie jar per test; use `request.newContext()` for tests that need isolated sessions.
- `--local` flag in `wrangler dev` does not support remote KV preview; all bindings must have local equivalents or test fixtures.
- Concurrent test files may conflict on stateful bindings; set `workers: 1` in `playwright.config.ts` for tests hitting shared KV or D1.

## Verification
```bash
# Run once against a running dev server
pnpm exec playwright test --headed

# CI run
CI=true pnpm exec playwright test

# View the HTML report after failure
pnpm exec playwright show-report
```

## Related
- `/documentation/docs/policies/devtools/vitest-pool-workers-cloudflare-test-api.md`
- `/documentation/docs/policies/devtools/wrangler-dev-local-d1-r2-kv.md`
- `/documentation/docs/policies/devtools/hono-test-utils-workers-unit-testing.md`
- `/documentation/docs/policies/devtools/local-https-dev-proxy-wrangler.md`

## Sources
- https://playwright.dev/docs/test-webserver
- https://developers.cloudflare.com/workers/testing/
- https://playwright.dev/docs/api/class-apirequestcontext
