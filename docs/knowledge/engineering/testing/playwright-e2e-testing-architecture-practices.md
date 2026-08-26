# Playwright End-to-End Testing — Architecture, Isolation, and CI Best Practices

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Cypress test suite takes 25 minutes in CI because tests run
sequentially in a single browser instance. Flaky tests fail with
"element not found" because explicit `cy.wait(2000)` calls do not
account for varying load times. Authentication is repeated in every
test file, adding 3 seconds per test. When a test fails in CI, the
only artifact is a screenshot — reproducing the failure locally
requires guessing what went wrong. Your tests use CSS selectors tied
to styling classes that break every time the design team updates
the component library.

## Context

Playwright is a browser automation framework from Microsoft that
drives real browser engines (Chromium, Firefox, WebKit) via the
browser protocol layer. Its core architecture principles — auto-
waiting, web-first assertions, test isolation via browser contexts,
and built-in parallelism — address the most common sources of E2E
test flakiness and slowness. Playwright provides a unified API
across all three engines plus mobile emulation, visual comparison
testing, API testing capabilities, and a trace viewer for debugging
CI failures. Tests verify user-visible behavior, not implementation
details.

## Auto-waiting and web-first assertions

```typescript
// Auto-waiting: before any action, Playwright waits for
// the element to be:
//   → Attached to DOM
//   → Visible
//   → Stable (not animating)
//   → Enabled
//   → Not obscured by other elements
// No manual sleep/waitForTimeout needed.

// Web-first assertions — retry until condition holds
// CORRECT: retries automatically until visible or timeout
await expect(page.getByText('Welcome')).toBeVisible();
await expect(page.getByRole('heading')).toHaveText('Dashboard');
await expect(page).toHaveURL('/dashboard');

// WRONG: snapshots state once, no retry, flaky
expect(await page.getByText('Welcome').isVisible()).toBe(true);
```

## Locator strategy

```typescript
// Prefer semantic/role locators (survive markup changes)
page.getByRole('button', { name: 'Submit' });
page.getByLabel('Email address');
page.getByPlaceholder('Search...');
page.getByTestId('checkout-button');

// Chain and filter locators
page.getByRole('listitem')
  .filter({ hasText: 'Product 2' })
  .getByRole('button', { name: 'Add to cart' });

// AVOID: CSS/XPath tied to styling or structure
page.locator('.btn-primary.mt-4 > span');  // fragile
page.locator('//div[3]/form/button');       // fragile
```

```
Locator priority (most to least resilient):

  1. getByRole      — mirrors assistive technology
  2. getByLabel     — form fields by label text
  3. getByTestId    — explicit test anchors
  4. getByText      — visible text content
  5. CSS selector   — only when nothing else works
  6. XPath          — avoid entirely
```

## Test isolation

```typescript
// Each test gets its own BrowserContext:
//   → Isolated cookies, localStorage, sessionStorage
//   → Isolated cache and network state
//   → No cross-test state leakage
//   → Safe for parallel execution

// Setup in beforeEach, not chained between tests
test.beforeEach(async ({ page }) => {
  await page.goto('/dashboard');
});

test('shows user profile', async ({ page }) => {
  await page.getByRole('link', { name: 'Profile' }).click();
  await expect(page.getByRole('heading')).toHaveText('Profile');
});

test('shows settings', async ({ page }) => {
  // Independent — doesn't depend on previous test
  await page.getByRole('link', { name: 'Settings' }).click();
  await expect(page.getByRole('heading')).toHaveText('Settings');
});
```

## Authentication reuse (storageState)

```typescript
// auth.setup.ts — run login ONCE
import { test as setup } from '@playwright/test';

setup('authenticate', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill('user@example.com');
  await page.getByLabel('Password').fill('password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL('/dashboard');

  await page.context().storageState({ path: 'auth.json' });
});
```

```typescript
// playwright.config.ts — reuse auth state
export default defineConfig({
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'tests',
      dependencies: ['setup'],
      use: { storageState: 'auth.json' },
    },
  ],
});
```

```
storageState persists:
  → Cookies
  → localStorage
  → IndexedDB

Does NOT persist:
  → sessionStorage (tab-scoped by design)

Security: auth.json contains live session credentials.
Never commit to repository. Add to .gitignore.
```

## Parallel execution and sharding

```typescript
// playwright.config.ts
export default defineConfig({
  workers: process.env.CI ? 4 : undefined,
  retries: process.env.CI ? 2 : 0,
  use: {
    headless: true,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
});

// Parallelize within a describe block
test.describe.configure({ mode: 'parallel' });
```

```bash
# Shard across CI machines (4 shards)
npx playwright test --shard=1/4
npx playwright test --shard=2/4
npx playwright test --shard=3/4
npx playwright test --shard=4/4

# Merge reports from shards
npx playwright merge-reports ./all-shard-reports

# 4 shards commonly cuts CI wall-clock time 60-70%
```

## Trace Viewer

```
Configuration:
  trace: 'on-first-retry'     → records on first retry only
  trace: 'retain-on-failure'  → keeps trace for failed tests

What trace records:
  → DOM snapshots at each action
  → Network requests and responses
  → Console logs
  → Screenshots per action step
  → Full action timeline

View traces:
  npx playwright show-trace trace.zip

Essential for debugging CI-only failures without
reproducing locally. Always enable in CI configuration.
```

## Page Object Model

```typescript
// pages/checkout.page.ts
export class CheckoutPage {
  constructor(private page: Page) {}

  async addItem(name: string) {
    await this.page.getByRole('button', { name: `Add ${name}` }).click();
  }

  async checkout() {
    await this.page.getByRole('button', { name: 'Checkout' }).click();
  }

  async expectTotal(amount: string) {
    await expect(this.page.getByTestId('total')).toHaveText(amount);
  }
}

// tests/checkout.spec.ts
test('checkout flow', async ({ page }) => {
  const checkout = new CheckoutPage(page);
  await checkout.addItem('Widget');
  await checkout.checkout();
  await checkout.expectTotal('$9.99');
});
```

## Visual comparison and API testing

```typescript
// Visual comparison — pixel-diff against baseline
await expect(page).toHaveScreenshot('dashboard.png', {
  maxDiffPixels: 100,
  threshold: 0.2,
});
// Baselines are OS/browser-specific
// Generate in CI to avoid local-vs-CI rendering drift

// API testing — no browser needed
const response = await request.post('/api/login', {
  data: { email: 'user@test.com', password: 'pass' },
});
expect(response.ok()).toBeTruthy();
const body = await response.json();
expect(body.token).toBeDefined();
```

## CI configuration

```yaml
# GitHub Actions with sharding
jobs:
  test:
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test --shard=${{ matrix.shard }}/4
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: traces-${{ matrix.shard }}
          path: test-results/
```

## Anti-patterns

- **Using `page.waitForTimeout()`** — hardcoded waits are flaky
  and slow. Playwright's auto-waiting and web-first assertions
  handle timing automatically. Explicit waits indicate a missing
  assertion.
- **CSS selectors tied to styling classes** — `.btn-primary.mt-4`
  breaks when design updates classes. Use role, label, or test-id
  locators that survive markup changes.
- **Sharing storageState across parallel workers** — when tests
  mutate server state (create/delete resources), a single shared
  auth state causes race conditions. Authenticate per worker.
- **Testing third-party sites** — testing external services you
  don't control (payment providers, OAuth) is unreliable. Mock
  external dependencies with route interception.
- **Disabling test isolation for speed** — removing browser
  context isolation introduces order-dependent flakiness that is
  harder to debug than the time saved.

## Gotchas

- **Visual baselines are platform-specific** — screenshots differ
  between macOS, Linux, and Windows due to font rendering. Generate
  baselines in CI (Linux) and update via CI, not locally.
- **`trace: 'on'` in CI creates large artifacts** — traces include
  full DOM snapshots and network data. Use `'on-first-retry'` or
  `'retain-on-failure'` to limit trace size.
- **`storageState` does not include sessionStorage** — by design,
  sessionStorage is tab-scoped. If your app relies on sessionStorage
  for auth, use a setup fixture that sets it explicitly.
- **Install only needed browsers** — `npx playwright install` grabs
  all three engines. Use `npx playwright install chromium` in CI to
  save time and disk if testing one engine.

## Verification

- Auto-waiting used instead of explicit wait/sleep calls.
- Semantic locators (getByRole, getByLabel) preferred over CSS.
- Each test isolated via independent browser context.
- Authentication reused via storageState setup project.
- Trace viewer enabled for CI failure debugging.
- Sharding configured for parallel CI execution.
- Visual baselines generated in CI environment.
- storageState files excluded from version control.

## Related

- `documentation/docs/policies/testing/visual-regression-testing-comparison.md`
- `documentation/docs/policies/testing/api-contract-testing-schema-validation.md`
- `documentation/docs/policies/frontend/react-19-server-components-streaming-ssr.md`

## Source URLs (verified 2026-08-16)

- Playwright — Best Practices (Official) — https://playwright.dev/docs/best-practices
- Playwright — Authentication / storageState — https://playwright.dev/docs/auth
- Playwright Best Practices 2026 — BrowserStack — https://www.browserstack.com/guide/playwright-best-practices
- Playwright Architecture — TestDino — https://testdino.com/blog/playwright-architecture
