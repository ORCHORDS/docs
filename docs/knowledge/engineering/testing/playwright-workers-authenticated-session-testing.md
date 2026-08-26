# Playwright E2E Testing Workers-Backed Authenticated Sessions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a Cloudflare Workers application with session-based authentication backed by a D1 database. You need Playwright E2E tests that cover login, protected routes, 401 responses on unauthorised requests, and session expiry — all running against a local `wrangler pages dev` server in CI.

## Context

Cloudflare Workers handle cookies natively via the `Set-Cookie` response header. Playwright's `page.request` API can make raw HTTP calls to obtain a session cookie, and `page.context().addCookies()` injects it into subsequent browser-driven requests. Worker-level fake clock support (available in `wrangler dev --local`) lets you simulate session expiry without waiting real wall-clock seconds.

## Playwright Auth Session Test Suite

```typescript
import { test, expect, Page, BrowserContext } from "@playwright/test";
import { D1Database } from "@cloudflare/workers-types";
import { execSync } from "node:child_process";
import crypto from "node:crypto";

const BASE_URL = process.env.WORKERS_BASE_URL ?? "http://localhost:8788";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function seedTestUser(
  email: string,
  password: string
): Promise<{ userId: string }> {
  const userId = crypto.randomUUID();
  const hash = crypto
    .createHash("sha256")
    .update(password)
    .digest("hex");

  // Seed directly via wrangler d1 execute (local)
  execSync(
    `npx wrangler d1 execute sessions-db --local --command \
    "INSERT INTO users (id, email, password_hash) VALUES ('${userId}', '${email}', '${hash}');"`
  );

  return { userId };
}

async function deleteTestUser(email: string): Promise<void> {
  execSync(
    `npx wrangler d1 execute sessions-db --local --command \
    "DELETE FROM users WHERE email = '${email}';"`
  );
}

async function login(
  context: BrowserContext,
  email: string,
  password: string
): Promise<string> {
  // Use Playwright's request API — no browser rendering needed
  const response = await context.request.post(`${BASE_URL}/auth/login`, {
    data: { email, password },
    headers: { "Content-Type": "application/json" },
  });

  expect(response.status()).toBe(200);

  // Extract session cookie from Set-Cookie header
  const setCookie = response.headers()["set-cookie"] ?? "";
  const match = setCookie.match(/session=([^;]+)/);
  if (!match) throw new Error("No session cookie in login response");
  const sessionToken = match[1];

  // Inject cookie into the browser context
  await context.addCookies([
    {
      name: "session",
      value: sessionToken,
      domain: new URL(BASE_URL).hostname,
      path: "/",
      httpOnly: true,
      secure: false, // local dev only
    },
  ]);

  return sessionToken;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

let testEmail: string;

test.beforeEach(async () => {
  testEmail = `test+${Date.now()}@example.com`;
  await seedTestUser(testEmail, "correct-horse-battery");
});

test.afterEach(async () => {
  await deleteTestUser(testEmail);
});

test("protected route returns 200 with valid session", async ({ context }) => {
  await login(context, testEmail, "correct-horse-battery");

  const res = await context.request.get(`${BASE_URL}/api/profile`);
  expect(res.status()).toBe(200);

  const body = await res.json();
  expect(body).toMatchObject({ email: testEmail });
});

test("protected route returns 401 without session cookie", async ({
  context,
}) => {
  // Do NOT call login — no cookie injected
  const res = await context.request.get(`${BASE_URL}/api/profile`, {
    // Ensure no cookies are sent
    headers: { Cookie: "" },
  });
  expect(res.status()).toBe(401);
});

test("login with wrong password returns 401", async ({ context }) => {
  const res = await context.request.post(`${BASE_URL}/auth/login`, {
    data: { email: testEmail, password: "<redacted-secret>" },
    headers: { "Content-Type": "application/json" },
  });
  expect(res.status()).toBe(401);
});

test("session expiry: expired token returns 401", async ({ context, page }) => {
  // Login to get a valid session
  await login(context, testEmail, "correct-horse-battery");

  // Advance the Worker's fake clock past the session TTL (e.g. 1 hour = 3600s)
  // Workers test helpers expose __clock via a special header in wrangler dev --local
  await context.request.post(`${BASE_URL}/__test/advance-clock`, {
    data: { seconds: 3601 },
    headers: { "Content-Type": "application/json" },
  });

  // Previously valid session should now be rejected
  const res = await context.request.get(`${BASE_URL}/api/profile`);
  expect(res.status()).toBe(401);

  const body = await res.json<{ error: string }>();
  expect(body.error).toMatch(/expired/i);
});

test("full browser flow: login page -> dashboard redirect", async ({ page }) => {
  await page.goto(`${BASE_URL}/login`);
  await page.fill('[name="email"]', testEmail);
  await page.fill('[name="password"]', "correct-horse-battery");
  await page.click('[type="submit"]');

  await page.waitForURL(`${BASE_URL}/dashboard`);
  expect(page.url()).toBe(`${BASE_URL}/dashboard`);

  // Verify the dashboard renders user-specific content
  await expect(page.locator('[data-testid="user-email"]')).toHaveText(
    testEmail
  );
});
```

## CI Configuration (`playwright.config.ts`)

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  webServer: {
    command: "npx wrangler pages dev dist --port 8788 --local",
    url: "http://localhost:8788",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
```

## Anti-patterns

- **Sharing a single test user across all tests** — parallel tests race on the same D1 row and produce intermittent failures.
- **Hardcoding session token values** in tests — tokens are time-bound and environment-specific; always obtain them dynamically via the login helper.
- **Skipping `page.context().addCookies()`** and instead manually appending `Cookie` headers on every request — brittle and misses domain/path matching.
- **Running Playwright tests against the production Workers deployment** — tests that mutate D1 data or advance a fake clock must only target local or a dedicated staging environment.

## Gotchas

- `wrangler pages dev` rebuilds on file change; in CI, build the bundle first (`npm run build`) then start the dev server against the built output to avoid mid-test rebuilds.
- The `__test/advance-clock` endpoint must be gated behind an environment flag (`ENABLE_TEST_ROUTES=true`) and must never be deployed to production.
- Cookie `secure: false` is required for `http://localhost` in Playwright. Flip it to `true` and add `sameSite: "None"` for HTTPS staging environments.
- `context.request` bypasses the browser's cookie jar. Cookies added via `addCookies` ARE used by subsequent `page.goto()` calls within the same context.

## Verification

```bash
# Start the local dev server separately (optional — playwright.config webServer handles this)
npx wrangler pages dev dist --port 8788 --local

# Run Playwright tests
npx playwright test e2e/auth.spec.ts

# Headed mode for debugging
npx playwright test e2e/auth.spec.ts --headed --slowMo=500
```

## Related

- `vitest-workers-kv-namespace-isolation.md`
- `workers-integration-test-service-bindings-miniflare.md`
- Playwright `addCookies` API docs

## Sources

- Playwright test documentation — `https://playwright.dev/docs/api/class-browsercontext#browser-context-add-cookies`
- Cloudflare Workers session management patterns
- `wrangler pages dev` CLI reference
