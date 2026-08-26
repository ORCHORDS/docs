# playwright-page-object-model

**Issue:** Organizing Playwright tests with Page Object Model to reduce duplication
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
E2e test suites with repeated selector strings across hundreds of tests. One UI change breaks dozens of tests.

## Pattern / Solution
```ts
// e2e/pages/LoginPage.ts
import { type Page, type Locator } from "@playwright/test";

export class LoginPage {
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly errorMessage: Locator;

  constructor(private page: Page) {
    this.emailInput = page.getByLabel("Email");
    this.passwordInput = page.getByLabel("Password");
    this.submitButton = page.getByRole("button", { name: "Sign in" });
    this.errorMessage = page.getByRole("alert");
  }

  async goto() { await this.page.goto("/login"); }

  async login(email: string, password: string) {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }
}

// e2e/auth.spec.ts
import { test, expect } from "@playwright/test";
import { LoginPage } from "./pages/LoginPage";

test("shows error for wrong password", async ({ page }) => {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.login("user@example.com", "wrong");
  await expect(loginPage.errorMessage).toBeVisible();
});
```

## Gotchas
- POM should encapsulate selectors, not assertions — keep expects in tests
- Avoid deep inheritance hierarchies in POMs
- Locators are lazy — no network call until interacted with

## Related
- `playwright-fixtures.md`
- `playwright-setup.md`
