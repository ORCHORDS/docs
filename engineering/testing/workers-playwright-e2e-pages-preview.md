# Playwright E2E Tests Against Cloudflare Pages Preview Deployments

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your project deploys to Cloudflare Pages and each PR generates a unique preview URL. You want Playwright E2E tests that run against those preview URLs in CI, authenticate via stored `storageState`, intercept Worker API calls to assert request payloads, capture screenshots on failure, and use `expect.soft` so one assertion failure doesn't abort the whole suite.

---

## Context
Cloudflare Pages exposes the preview URL as `$CF_PAGES_URL` during build-triggered deploys, and most CI providers let you pass it downstream as a custom environment variable (e.g. `PLAYWRIGHT_BASE_URL`). Playwright's `storageState` persists cookies and `localStorage` from a prior login step so subsequent tests skip the auth flow entirely. `page.route()` / `page.waitForRequest()` let you assert that your front-end called the correct Worker endpoint with the right body, without needing to own the Worker side in the E2E suite. `expect.soft` accumulates failures instead of throwing on the first one, which is valuable for visual regression checks.

---

## Setup / Config

```bash
# Install Playwright and its browser binaries
npm install --save-dev @playwright/test
npx playwright install chromium
```

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
  ],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "setup",
      testMatch: "**/auth.setup.ts",
    },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "e2e/.auth/user.json",
      },
      dependencies: ["setup"],
    },
  ],
});
```

## Implementation

```typescript
// e2e/auth.setup.ts — runs once, saves storageState
import { test as setup, expect } from "@playwright/test";
import * as path from "path";

const authFile = path.join(__dirname, ".auth/user.json");

setup("authenticate", async ({ page }) => {
  // Navigate to the login page on the preview deployment
  await page.goto("/login");

  await page.getByLabel("Email").fill(process.env.TEST_USER_EMAIL ?? "test@example.com");
  await page.getByLabel("Password").fill(process.env.TEST_USER_PASSWORD ?? "s3cr3t");
  await page.getByRole("button", { name: "Sign in" }).click();

  // Wait until the dashboard is visible — confirms the login succeeded
  await page.waitForURL("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // Persist auth state for all subsequent tests
  await page.context().storageState({ path: authFile });
});
```

```typescript
// e2e/products.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Products page", () => {
  test("loads product list and calls Workers API", async ({ page }) => {
    // Intercept the Worker API call before navigating
    const apiCallPromise = page.waitForRequest(
      (req) =>
        req.url().includes("/api/products") && req.method() === "GET"
    );

    await page.goto("/products");

    // Assert the Worker was called
    const apiCall = await apiCallPromise;
    expect(apiCall.headers()["accept"]).toContain("application/json");

    // Soft assertions — page keeps running even if one fails
    await expect.soft(
      page.getByRole("heading", { name: "Products" })
    ).toBeVisible();

    await expect.soft(
      page.getByTestId("product-card").first()
    ).toBeVisible();

    await expect.soft(
      page.getByText("Widget Pro")
    ).toBeVisible();

    // Hard assertion — must pass or test stops
    await expect(page.getByTestId("product-list")).not.toBeEmpty();
  });

  test("submits an order and asserts POST body to Worker", async ({ page }) => {
    // Intercept POST /api/orders to assert payload
    const orderRequestPromise = page.waitForRequest(
      (req) =>
        req.url().includes("/api/orders") && req.method() === "POST"
    );

    await page.goto("/products");
    await page.getByText("Widget Pro").click();
    await page.getByLabel("Quantity").fill("2");
    await page.getByRole("button", { name: "Add to Cart" }).click();
    await page.getByRole("button", { name: "Checkout" }).click();

    // Wait for the POST request to fire
    const orderRequest = await orderRequestPromise;
    const body = JSON.parse(orderRequest.postData() ?? "{}") as {
      productId: string;
      quantity: number;
    };

    expect(body.quantity).toBe(2);
    expect(typeof body.productId).toBe("string");

    // Assert the confirmation page loaded
    await page.waitForURL(/\/orders\/[\w-]+/);
    await expect(
      page.getByRole("heading", { name: /Order confirmed/i })
    ).toBeVisible();
  });

  test("screenshot is captured automatically on failure", async ({ page }) => {
    // Playwright captures a screenshot because screenshot: 'only-on-failure' is set
    await page.goto("/products");

    // Use expect.soft so test continues to completion even if banner is absent
    await expect.soft(
      page.getByTestId("promotional-banner")
    ).toBeVisible({ timeout: 2000 });

    // Confirm basic page structure regardless
    await expect(
      page.getByRole("main")
    ).toBeVisible();
  });
});
```

## CI Integration

```yaml
# .github/workflows/e2e.yml
name: E2E Tests

on:
  pull_request:

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Node.js
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci
      - run: npx playwright install --with-deps chromium

      - name: Wait for Pages preview
        run: |
          echo "PLAYWRIGHT_BASE_URL=${{ vars.CF_PAGES_PREVIEW_URL }}" >> $GITHUB_ENV

      - name: Run Playwright tests
        env:
          PLAYWRIGHT_BASE_URL: ${{ env.PLAYWRIGHT_BASE_URL }}
          TEST_USER_EMAIL: ${{ secrets.TEST_USER_EMAIL }}
          TEST_USER_PASSWORD: ${{ secrets.TEST_USER_PASSWORD }}
        run: npx playwright test

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: playwright-report/
```

---

## Anti-patterns
- **Hard-coding the base URL** — always read from `PLAYWRIGHT_BASE_URL` so the same test file runs locally and against any preview.
- **Re-authenticating inside every test** — `storageState` is the official Playwright pattern; re-logging in each `test()` call multiplies test time significantly.
- **Using `page.pause()` or `waitForTimeout()` in CI** — replace with `waitForRequest`, `waitForURL`, or `waitForSelector` to avoid flaky sleep-based synchronisation.
- **Ignoring soft assertion failures** — `expect.soft` collects failures but the test still reports as failed at the end; don't use it to mask real regressions.

---

## Gotchas
- Cloudflare Pages preview URLs include branch names and can contain slashes; URL-encode them if passing as a shell variable.
- `page.waitForRequest()` must be called **before** the action that triggers the request — set up the promise first, then click the button.
- `storageState` captures the full cookie jar including CSRF tokens; if your app rotates tokens on each page load the stored state may expire mid-run.
- Screenshots are saved to `test-results/` by default; configure `outputDir` in `playwright.config.ts` if your CI artifact step expects a different path.
- `expect.soft` failures accumulate silently; always check `test.info().errors` or the HTML report to see the full list.

---

## Verification

```bash
# Run against local dev server
PLAYWRIGHT_BASE_URL=http://localhost:5173 npx playwright test

# Run against a specific Pages preview URL
PLAYWRIGHT_BASE_URL=https://my-branch.pages.dev npx playwright test

# Run only product tests in headed mode for debugging
npx playwright test e2e/products.spec.ts --headed

# Open the last HTML report
npx playwright show-report
```

---

## Related
- `workers-integration-test-d1-seed-fixtures.md`
- `workers-vitest-env-bindings-mock-service.md`

---

## Sources
- Playwright storageState docs — https://playwright.dev/docs/auth
- Cloudflare Pages preview deployments — https://developers.cloudflare.com/pages/configuration/preview-deployments/
- Playwright network interception — https://playwright.dev/docs/network
