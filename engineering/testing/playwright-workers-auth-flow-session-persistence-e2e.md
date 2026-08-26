# Playwright Workers Auth Flow Session Persistence E2E

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Worker issues signed session cookies (HttpOnly, Secure, SameSite=Lax) after OAuth or credential login, and downstream Worker routes gate access via those cookies. Manually clicking through login in every test run is slow; sharing a single browser state file across tests causes race conditions and order-dependent failures. You need a Playwright strategy that authenticates once per test-project, persists the session to a `storageState` file, and replays it across all authenticated tests — while also verifying that session expiry, logout, and cookie rotation work correctly.

## Context

Cloudflare Workers handle auth at the edge without a traditional server session store. The typical pattern is:

1. `/auth/login` exchanges credentials for a signed JWT or opaque token
2. The Worker sets `Set-Cookie: session=<token>; HttpOnly; Secure; SameSite=Lax; Path=/`
3. All subsequent requests carry the cookie; the Worker validates the signature on each edge invocation

Playwright's `storageState` serialises cookies and `localStorage` to a JSON file. When a test opens a new `BrowserContext` with `storageState`, the saved cookies are injected — no login UI is shown. The challenge is keeping that file fresh (token TTL), isolating it per test-project (admin vs. regular user), and testing the sad paths (expired session, logout, CSRF rotation) without polluting the shared state.

## 1. Project Layout

```
playwright.config.ts
tests/
  auth.setup.ts          # global setup that produces storageState files
  auth-expiry.spec.ts    # tests that manipulate cookie TTL
  dashboard.spec.ts      # authenticated tests that reuse storageState
.auth/
  user.json              # written by auth.setup.ts, gitignored
  admin.json
```

```gitignore
# .gitignore
.auth/
```

## 2. Playwright Config: Projects and Dependencies

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: process.env.WORKER_URL ?? "http://localhost:8788",
    trace: "on-first-retry",
  },
  projects: [
    // Setup projects — run once, produce storageState files
    { name: "setup:user", testMatch: /auth\.setup\.ts/, use: { storageState: undefined } },
    { name: "setup:admin", testMatch: /auth\.setup\.ts/, use: { storageState: undefined } },

    // Authenticated suites depend on setup
    {
      name: "dashboard",
      testMatch: /dashboard\.spec\.ts/,
      dependencies: ["setup:user"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: ".auth/user.json",
      },
    },
    {
      name: "admin",
      testMatch: /admin\.spec\.ts/,
      dependencies: ["setup:admin"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: ".auth/admin.json",
      },
    },
    // Unauthenticated suite — no storageState dependency
    {
      name: "public",
      testMatch: /public\.spec\.ts/,
      use: devices["Desktop Chrome"],
    },
  ],
});
```

## 3. Auth Setup: Login Once and Save State

```typescript
// tests/auth.setup.ts
import { test as setup, expect } from "@playwright/test";
import path from "path";

const USER_AUTH_FILE = path.join(".auth", "user.json");
const ADMIN_AUTH_FILE = path.join(".auth", "admin.json");

setup("authenticate as regular user", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.TEST_USER_EMAIL!);
  await page.getByLabel("Password").fill(process.env.TEST_USER_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();

  // Wait for the Worker to redirect after successful auth
  await page.waitForURL("/dashboard");
  // Confirm the session cookie is present (HttpOnly → not accessible via JS,
  // but we can assert the redirected page is authenticated)
  await expect(page.getByRole("heading", { name: /dashboard/i })).toBeVisible();

  await page.context().storageState({ path: USER_AUTH_FILE });
});

setup("authenticate as admin", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.TEST_ADMIN_EMAIL!);
  await page.getByLabel("Password").fill(process.env.TEST_ADMIN_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();

  await page.waitForURL("/admin");
  await expect(page.getByRole("heading", { name: /admin panel/i })).toBeVisible();

  await page.context().storageState({ path: ADMIN_AUTH_FILE });
});
```

## 4. Authenticated Tests Reusing Persisted State

```typescript
// tests/dashboard.spec.ts
import { test, expect } from "@playwright/test";

// storageState: ".auth/user.json" injected via playwright.config.ts project

test("dashboard loads protected data without re-authenticating", async ({ page }) => {
  // Navigate directly — no login page because cookie is replayed
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /dashboard/i })).toBeVisible();
  await expect(page.getByTestId("user-email")).toContainText(process.env.TEST_USER_EMAIL!);
});

test("API endpoint returns 200 with session cookie in context", async ({ request }) => {
  // Playwright's APIRequestContext also honours storageState cookies
  const res = await request.get("/api/me");
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.email).toBe(process.env.TEST_USER_EMAIL);
});

test("navigating to /admin redirects regular user to 403", async ({ page }) => {
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/403|\/forbidden/);
});
```

## 5. Logout and Cookie Invalidation

```typescript
// tests/auth-expiry.spec.ts
import { test, expect } from "@playwright/test";

// This test runs WITHOUT a pre-authenticated storageState
// so it gets a fresh context each time

test.use({ storageState: undefined });

test("logout clears session and redirects to login", async ({ page }) => {
  // Authenticate inline for this test only
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.TEST_USER_EMAIL!);
  await page.getByLabel("Password").fill(process.env.TEST_USER_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("/dashboard");

  // Perform logout
  await page.getByRole("button", { name: /log out/i }).click();
  await page.waitForURL("/login");

  // Session cookie must be gone — direct navigation is rejected
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});

test("expired session cookie causes redirect to login", async ({ page, context }) => {
  // Inject a cookie with past expiry date to simulate TTL elapse
  await context.addCookies([
    {
      name: "session",
      value: "expired.signed.token",
      domain: new URL(process.env.WORKER_URL ?? "http://localhost:8788").hostname,
      path: "/",
      httpOnly: true,
      secure: false,   // false for localhost
      sameSite: "Lax",
      expires: Math.floor(Date.now() / 1000) - 3600, // 1 h in the past
    },
  ]);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
```

## 6. CSRF Token Rotation Assertion

```typescript
test("CSRF token rotates on each authenticated page load", async ({ page }) => {
  // storageState: ".auth/user.json" is active for this project
  await page.goto("/dashboard");

  const getToken = async () => {
    const meta = page.locator('meta[name="csrf-token"]');
    return meta.getAttribute("content");
  };

  const token1 = await getToken();
  expect(token1).toBeTruthy();

  // Hard reload triggers a new Worker invocation → new CSRF token
  await page.reload();
  const token2 = await getToken();
  expect(token2).not.toBe(token1);
});
```

## Anti-patterns

- **Single shared `storageState` for all users**: Admin and regular-user cookies collide, causing role-assertion tests to produce false passes.
- **Logging in inside every `test()` body**: Multiplies login round-trips, slows the suite, and causes rate-limiting against a live Worker when many tests run in parallel.
- **Committing `.auth/*.json` to git**: Session cookies are secrets; `.auth/` must be in `.gitignore` and regenerated in CI via secrets injection.
- **Using `page.waitForTimeout()` after login**: Flaky. Use `page.waitForURL()` or `expect(locator).toBeVisible()` to confirm the Worker's redirect has completed.
- **Testing session expiry by sleeping**: Use `context.addCookies()` with a past `expires` value instead of sleeping until the real TTL elapses.

## Gotchas

- Cloudflare's `Set-Cookie` with `Secure` flag is sent on HTTPS only. In local Wrangler dev (`--local`, HTTP), cookies arrive without `Secure`, so you may need to `secure: false` in `addCookies` for localhost tests.
- When a Worker rotates the session cookie on every request (sliding expiry), the `storageState` file is stale after the first test in a suite mutates the cookie jar. Playwright does NOT automatically update the file during a run — re-run setup if tests start failing with 401s.
- `request` fixture (APIRequestContext) and `page` fixture share the same cookie jar within a single test, but separate tests always get independent contexts.
- HttpOnly cookies are NOT visible via `page.evaluate(() => document.cookie)`. Assert auth state via page content or API responses, not cookie inspection.
- If your Worker checks the `Origin` header for CSRF, Playwright's `request` fixture sends requests with no `Origin` by default; add `extraHTTPHeaders: { Origin: baseURL }` for API tests.

## Verification

```bash
# Run with local Wrangler dev server in background
npx wrangler dev --local &

# Execute full E2E suite including setup projects
npx playwright test --project=setup:user --project=setup:admin
npx playwright test --project=dashboard --project=admin

# Check the storageState files exist and contain cookies
ls -la .auth/
```

## Related

- `playwright-authentication-state.md` — generic storageState fundamentals
- `auth-flow-testing-strategy.md` — unit-level token signing/verification
- `playwright-workers-turnstile-captcha-e2e.md` — CAPTCHA bypass with test keys during E2E
- `playwright-fixtures.md` — factory fixtures for per-test authenticated contexts

## Sources

- Playwright authentication docs: https://playwright.dev/docs/auth
- Cloudflare Workers cookie security: https://developers.cloudflare.com/workers/examples/auth-with-headers/
- OWASP session management: https://owasp.org/www-project-cheat-sheets/cheatsheets/Session_Management_Cheat_Sheet.html
