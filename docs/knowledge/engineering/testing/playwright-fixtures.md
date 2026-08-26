# playwright-fixtures

**Issue:** Sharing reusable setup/teardown and page objects via Playwright fixtures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Copy-pasting `new LoginPage(page)` into every test file. Fixtures solve this cleanly.

## Pattern / Solution
```ts
// e2e/fixtures.ts
import { test as base } from "@playwright/test";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";

type Fixtures = {
  loginPage: LoginPage;
  dashboardPage: DashboardPage;
  authenticatedPage: Page;
};

export const test = base.extend<Fixtures>({
  loginPage: async ({ page }, use) => {
    await use(new LoginPage(page));
  },
  dashboardPage: async ({ page }, use) => {
    await use(new DashboardPage(page));
  },
  authenticatedPage: async ({ page }, use) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("admin@example.com");
    await page.getByLabel("Password").fill("password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await use(page);
  },
});

export { expect } from "@playwright/test";
```

Usage:
```ts
import { test, expect } from "./fixtures";

test("shows dashboard after login", async ({ authenticatedPage }) => {
  await expect(authenticatedPage.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});
```

## Gotchas
- Fixtures are scoped: `test` (default), `worker`, or `page`
- Worker-scoped fixtures run once per parallel worker
- Circular fixture dependencies cause a runtime error

## Related
- `playwright-page-object-model.md`
- `playwright-authentication-state.md`
