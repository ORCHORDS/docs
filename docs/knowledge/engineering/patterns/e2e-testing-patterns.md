# e2e-testing-patterns

**Issue:** End-to-end testing — Playwright, Cypress, real environments
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your unit tests pass. Your integration tests pass. The app
breaks in production. The "search" feature works in
staging but not in production. The "login" flow has a
state bug you never caught.

## Root cause
**Unit + integration tests don't catch the full system.**
They test pieces. E2E tests test the whole thing.

**Source:** Playwright:
https://playwright.dev/

> "End-to-end testing is a methodology used to test whether
> the flow of an application is performing as designed from
> start to finish."

## The "test pyramid" revisited

```
       /\
      /E2E\  - Few, slow, full system
     /------\
    / Integ  \ - Some, medium, glue
   /----------\
  /   Unit     \ - Many, fast, logic
 /--------------\
```

E2E tests are the fewest, slowest, and most expensive. They
catch issues the lower levels miss.

## The "what to test in E2E" decision

Test in E2E:
- ✅ **Critical user flows:** signup, login, checkout,
  password reset
- ✅ **Cross-cutting concerns:** auth + DB + UI together
- ✅ **Third-party integrations:** payments, email, OAuth
- ✅ **Multi-step flows:** onboarding, multi-page forms

Don't test in E2E:
- ❌ **Logic that's already in unit tests**
- ❌ **Edge cases** (use unit tests for these)
- ❌ **Slow flows** (test the slow part in unit tests; the
  end-to-end in E2E)

## The "Playwright" pattern

```ts
// tests/e2e/login.spec.ts
import { test, expect } from '@playwright/test';

test('user can log in', async ({ page }) => {
  await page.goto('https://staging.example.com/login');
  await page.fill('[name="email"]', 'test@example.com');
  await page.fill('[name="password"]', 'password123');
  await page.click('button[type="submit"]');

  // Verify redirect to dashboard
  await expect(page).toHaveURL(/dashboard/);

  // Verify user info is displayed
  await expect(page.locator('.user-menu')).toContainText('test@example.com');
});

test('login fails with wrong password', async ({ page }) => {
  await page.goto('https://staging.example.com/login');
  await page.fill('[name="email"]', 'test@example.com');
  await page.fill('[name="password"]', 'wrong');
  await page.click('button[type="submit"]');

  // Verify error message
  await expect(page.locator('.error')).toContainText('Invalid credentials');
});
```

## The "test data" pattern

For repeatable E2E tests, use a known test data set:
```ts
// tests/e2e/fixtures.ts
export const testUsers = {
  admin: { email: 'admin@test.com', password: 'adminPass1!' },
  user: { email: 'user@test.com', password: 'userPass1!' },
};

// Setup: create these users in the test DB
test.beforeAll(async () => {
  await seedTestUsers();
});

// Teardown: clean up
test.afterAll(async () => {
  await cleanupTestUsers();
});
```

## The "page object" pattern

For maintainable E2E tests, use page objects:
```ts
// pages/login.page.ts
export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/login');
  }

  async login(email: string, password: string) {
    await this.page.fill('[name="email"]', email);
    await this.page.fill('[name="password"]', password);
    await this.page.click('button[type="submit"]');
  }

  async expectError(message: string) {
    await expect(this.page.locator('.error')).toContainText(message);
  }
}

// tests/e2e/login.spec.ts
test('login fails with wrong password', async ({ page }) => {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.login('test@example.com', 'wrong');
  await loginPage.expectError('Invalid credentials');
});
```

The page object encapsulates the UI; the test is readable.

## The "environment" pattern

For E2E tests, use a real environment:
- **Staging:** dedicated environment, real DB, real CDN
- **Preview environment:** per-PR, ephemeral
- **Production-like:** mirror of production (different URL)

The closer to production, the more the tests catch.

## The "browser matrix" pattern

Test in multiple browsers:
```ts
// playwright.config.ts
export default defineConfig({
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'mobile-chrome', use: { ...devices['Pixel 5'] } },
    { name: 'mobile-safari', use: { ...devices['iPhone 13'] } },
  ],
});
```

The same test runs in 5 browsers. Catches browser-specific
bugs.

## The "parallelism" pattern

For fast CI, run tests in parallel:
```ts
// playwright.config.ts
export default defineConfig({
  workers: 4,  // 4 parallel workers
  retries: 2,  // Retry flaky tests
});
```

For 100 tests, 4 workers = 4x faster. But: 4 workers = 4x
load on the test environment.

## The "retry" pattern

For flaky tests, retry on failure:
```ts
// playwright.config.ts
export default defineConfig({
  retries: 2,
});
```

The first run is allowed to fail; the second run is the
verdict. A test that fails 3 times is broken.

## The "trace viewer" pattern

For debugging failures, Playwright has a trace viewer:
```ts
// playwright.config.ts
export default defineConfig({
  use: {
    trace: 'on-first-retry',  // Trace on retry
  },
});
```

The trace shows: network, console, screenshots, video, DOM
snapshot. Open the trace in the trace viewer for a step-by-
step replay.

## The "visual regression" integration

Playwright supports visual snapshots (see
`visual-regression-testing.md`):
```ts
test('homepage visual snapshot', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveScreenshot('homepage.png');
});
```

## The "CI integration" pattern

```yaml
# .github/workflows/e2e.yml
name: E2E Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npx playwright install --with-deps
      - run: npx playwright test
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
```

The CI runs the tests; the artifacts (trace, report) are
uploaded on failure.

## The "production-like data" pattern

For meaningful E2E tests, use production-scale data:
- 1M users in the DB (not 10)
- 100k posts (not 100)
- Realistic data shape (not synthetic)

A test that "passes" on 10 users may fail on 1M users.

## Verification
- **Test:** E2E tests pass in CI
- **Live:** E2E tests run on every PR
- **Audit:** Quarterly review of E2E coverage

## Gotchas
- **E2E tests are slow.** A 100-test suite takes 5-10 min.
  Run them on a separate schedule (nightly, pre-release).
- **E2E tests are flaky.** Network issues, timing issues,
  environment issues. Add retries; investigate flakes.
- **E2E tests are brittle.** A UI change breaks tests.
  Use stable selectors (`data-testid`) not CSS classes.
- **E2E tests are not unit tests.** Don't test logic in E2E.
  Test the flow; trust the unit tests.
- **E2E tests need maintenance.** Every UI change updates
  multiple tests. Budget for it.
- **E2E tests are not free in CI.** 100 tests × 5 min = 8
  hours/day of CI time. Use preview environments for PRs.

## Related
- `test-pyramid.md`
- `unit-testing-patterns.md`
- `visual-regression-testing.md`
- `preview-environments.md`
- Playwright: https://playwright.dev/
- Cypress: https://www.cypress.io/
