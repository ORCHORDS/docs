# test-pyramid

**Issue:** Unit, integration, e2e — what to test at which level
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 1000 unit tests, 50 integration tests, 0 end-to-end
tests. You ship a feature. It works in unit tests. It works in
integration tests. It fails in production because the UI
doesn't pass the right cookie. You had no way to know.

## Root cause
**The test pyramid is a guideline for what to test at each
level.** Unit tests are fast + cheap but don't catch
integration issues. E2E tests are slow + expensive but catch
real-world failures. A healthy test suite has all three layers.

**Source:** Martin Fowler — Test Pyramid:
https://martinfowler.com/bliki/TestPyramid.html

> "The test pyramid is a way of thinking about the different
> levels of testing ... and how much of each you should have."

## The three levels

### Level 1: Unit tests (70-80% of tests)
- **What:** Test a single function in isolation
- **Speed:** < 1ms per test
- **Coverage:** All branches, edge cases
- **Tools:** vitest, jest
- **Example:** `test/dora.test.ts` — test the DORA control
  validation logic

### Level 2: Integration tests (15-25% of tests)
- **What:** Test multiple components together (function +
  database, or function + external API)
- **Speed:** 10-100ms per test
- **Coverage:** Real data flow, no mocks
- **Tools:** vitest + @cloudflare/vitest-pool-workers (D1
  in-memory)
- **Example:** `test/auditDO.test.ts` — test the DO + D1
  interaction

### Level 3: End-to-end (E2E) tests (5-10% of tests)
- **What:** Test the full user flow (browser + UI + API + DB)
- **Speed:** 1-10s per test
- **Coverage:** Critical user paths (signup, login, checkout)
- **Tools:** Playwright, Cypress
- **Example:** `test/e2e/signup.test.ts` — sign up via the UI

## Anti-patterns

### The inverted pyramid (too many E2E)
- 1000 E2E tests, 50 integration tests, 10 unit tests
- Slow CI (> 30 minutes)
- Flaky (E2E is more susceptible to environment issues)
- Hard to maintain

### The "all unit" anti-pattern
- 5000 unit tests, 0 integration, 0 E2E
- Fast CI
- Misses real-world integration issues
- Production failures

### The "no tests" anti-pattern
- 0 tests at any level
- "We'll add tests later" (you won't)
- Production is the test environment

## What to test where

| Test target | Level |
|---|---|
| Pure functions (string manipulation, math, validation) | Unit |
| Class methods (with no I/O) | Unit |
| Database CRUD (read, write, update) | Integration |
| API endpoints (with DB) | Integration |
| Authentication flows | Integration + E2E |
| Payment flows | E2E |
| User-visible UI behavior | E2E |
| Critical user journeys (signup → first action) | E2E |
| Performance (load testing) | E2E + specialized tools (k6, etc.) |

## Vitest configuration for CF Workers

For integration tests with D1 (in-memory):
```ts
// vitest.config.ts
import { cloudflareTest } from '@cloudflare/vitest-pool-workers';

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: './wrangler.toml' },
    }),
  ],
});
```

This gives you real D1, real DO, real KV — all in-memory,
in-Worker. Tests run in <100ms each.

## E2E with Playwright

```ts
// test/e2e/signup.test.ts
import { test, expect } from '@playwright/test';

test('user can sign up and log in', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.click('text=Sign up');
  await page.fill('input[name="email"]', 'test@example.com');
  await page.fill('input[name="password"]', 'MySecurePassword123!');
  await page.click('button[type="submit"]');

  // Verify redirect
  await expect(page).toHaveURL(/.*\/dashboard/);

  // Verify authenticated state
  await expect(page.locator('text=Welcome')).toBeVisible();
});
```

## Verification
- **Test:** `npm test` runs in <5 minutes total
- **Test:** Unit:Integration:E2E ratio is ~70:25:5
- **Live:** The 5 critical user journeys have E2E coverage
- **Audit:** Quarterly review of test coverage + flakiness

## Gotchas
- **E2E tests are flaky.** Use `expect(...).toBeVisible()` not
  `expect(...).toBeDefined()`. Wait for elements, don't assume
  timing.
- **Don't mock the database in integration tests.** That makes
  them unit tests. The value of integration tests is the real
  DB query.
- **Snapshot tests are useful but risky.** They catch
  unintended changes (good) but require maintenance (bad).
  Use sparingly.
- **Test isolation is hard.** Each test should be independent.
  No test should depend on another test's state. Use a
  beforeEach to reset.
- **Test data is real PII.** Generate test data with
  `@faker-js/faker`, not real user data.
- **The test pyramid is a guide, not a rule.** Some apps need
  more integration tests; some need more E2E. Adjust based on
  what fails in production.

## Related
- `patterns/observability-three-pillars.md` (test in production
  too)
- `audit-log-mandatory.md` (test the audit log is written)
- Martin Fowler: https://martinfowler.com/bliki/TestPyramid.html
- Playwright: https://playwright.dev/
