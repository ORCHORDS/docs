# End-to-End Testing Workers-Backed Apps with Playwright

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your front-end app talks to a Worker API for authentication, product listings, and checkout. Unit and integration tests pass, but the full flow — sign in, add to cart, checkout — has never been tested as a user experiences it in a real browser. A change to the Worker's cookie-setting logic or a CORS header breaks the front-end silently.

## Context

Playwright is a browser automation framework that controls Chromium, Firefox, and WebKit via CDP/BiDi. For Workers-backed apps the strategy is:

1. **globalSetup** starts `wrangler dev --local` and any front-end dev server.
2. Playwright tests hit `http://localhost:PORT` as a real browser would.
3. **Cookie injection** bypasses the login UI for tests that focus on post-auth flows.
4. **Visual regression** snapshots are stored as PNG baselines and compared on each run.
5. **Test artifacts** (screenshots, traces, videos) are uploaded to R2 for long-term storage.

This setup tests the complete request path: Browser → Worker → D1/KV/Queue — without mocking any layer.

## Solution

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'playwright-report/results.json' }],
  ],
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  globalSetup: './tests/e2e/global-setup.ts',
  globalTeardown: './tests/e2e/global-teardown.ts',
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox',  use: { ...devices['Desktop Firefox'] } },
    { name: 'mobile',   use: { ...devices['iPhone 15'] } },
  ],
});
```

```typescript
// tests/e2e/global-setup.ts
import { ChildProcess, spawn } from 'child_process';
import { writeFileSync } from 'fs';

declare global {
  // eslint-disable-next-line no-var
  var __WRANGLER_PROC__: ChildProcess;
  var __FRONTEND_PROC__: ChildProcess;
}

async function waitForPort(port: number, retries = 30): Promise<void> {
  for (let i = 0; i < retries; i++) {
    try {
      await fetch(`http://localhost:${port}/health`);
      return;
    } catch {}
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Port ${port} not ready after ${retries} attempts`);
}

export default async function globalSetup() {
  // 1. Start the Worker in local mode
  global.__WRANGLER_PROC__ = spawn(
    'npx',
    ['wrangler', 'dev', '--local', '--port', '8787', '--env', 'test'],
    { stdio: 'pipe', detached: false }
  );

  // 2. Start the front-end dev server (Vite, Next.js, etc.)
  global.__FRONTEND_PROC__ = spawn(
    'npx',
    ['vite', '--port', '5173', '--mode', 'test'],
    { stdio: 'pipe', detached: false }
  );

  await Promise.all([
    waitForPort(8787),
    waitForPort(5173),
  ]);

  // 3. Seed test data via the Worker's test state endpoint
  await fetch('http://localhost:8787/__test/seed', { method: 'POST' });

  // 4. Obtain a valid session cookie for authenticated tests
  const loginRes = await fetch('http://localhost:8787/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'e2e@example.com', password: '<redacted-secret>' }),
  });
  const { token } = await loginRes.json<{ token: string }>();

  // 5. Write the session token to a temp file for tests to read
  writeFileSync('/tmp/e2e-session.json', JSON.stringify({ token }), 'utf-8');

  console.log('[global-setup] Worker and front-end ready');
}
```

```typescript
// tests/e2e/global-teardown.ts
import { uploadArtifactsToR2 } from './helpers/r2-upload';

export default async function globalTeardown() {
  global.__WRANGLER_PROC__?.kill();
  global.__FRONTEND_PROC__?.kill();

  // Upload Playwright artifacts to R2 for long-term storage
  if (process.env.CI) {
    await uploadArtifactsToR2({
      bucket: process.env.R2_BUCKET ?? 'playwright-artifacts',
      accountId: process.env.CF_ACCOUNT_ID!,
      apiToken: process.env.CF_API_TOKEN!,
      localDir: 'playwright-report',
      prefix: `runs/${process.env.GITHUB_RUN_ID ?? Date.now()}`,
    });
  }
}
```

```typescript
// tests/e2e/helpers/r2-upload.ts
import { readdirSync, readFileSync, statSync } from 'fs';
import path from 'path';

interface R2UploadOptions {
  bucket: string;
  accountId: string;
  apiToken: string;
  localDir: string;
  prefix: string;
}

export async function uploadArtifactsToR2(opts: R2UploadOptions): Promise<void> {
  const files = readdirSync(opts.localDir, { recursive: true }) as string[];

  await Promise.allSettled(
    files
      .filter((f) => statSync(path.join(opts.localDir, f)).isFile())
      .map(async (file) => {
        const body = readFileSync(path.join(opts.localDir, file));
        const key  = `${opts.prefix}/${file}`;

        await fetch(
          `https://api.cloudflare.com/client/v4/accounts/${opts.accountId}/r2/buckets/${opts.bucket}/objects/${encodeURIComponent(key)}`,
          {
            method: 'PUT',
            headers: {
              Authorization: `Bearer ${opts.apiToken}`,
              'Content-Type': 'application/octet-stream',
            },
            body,
          }
        );
      })
  );
}
```

```typescript
// tests/e2e/checkout.spec.ts
import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';

function getSession() {
  return JSON.parse(readFileSync('/tmp/e2e-session.json', 'utf-8')) as { token: string };
}

test.describe('Checkout flow', () => {
  test.beforeEach(async ({ context }) => {
    // Inject auth cookie so tests start already logged in
    const { token } = getSession();
    await context.addCookies([{
      name: 'session',
      value: token,
      domain: 'localhost',
      path: '/',
      httpOnly: true,
      secure: false,
    }]);
  });

  test('user can add a product to cart and complete checkout', async ({ page }) => {
    await page.goto('/products/abc-123');
    await expect(page.getByRole('heading', { name: 'Widget Pro' })).toBeVisible();

    await page.getByRole('button', { name: 'Add to cart' }).click();
    await expect(page.getByTestId('cart-count')).toHaveText('1');

    await page.getByRole('link', { name: 'Checkout' }).click();
    await page.getByLabel('Card number').fill('4242 4242 4242 4242');
    await page.getByLabel('Expiry').fill('12/30');
    await page.getByLabel('CVC').fill('123');
    await page.getByRole('button', { name: 'Pay now' }).click();

    await expect(page.getByRole('heading', { name: 'Order confirmed' })).toBeVisible();
    await expect(page.getByTestId('order-id')).not.toBeEmpty();
  });

  test('visual regression — product page', async ({ page }) => {
    await page.goto('/products/abc-123');
    await expect(page).toHaveScreenshot('product-page.png', { maxDiffPixelRatio: 0.02 });
  });
});
```

## Implementation Details

**Parallel test execution** — Playwright runs spec files in parallel by default. Set `workers: 4` in CI so each Worker runs an isolated browser context. The `wrangler dev` local instance handles concurrent requests safely; local Miniflare is stateless per request.

**Cookie injection** — using `context.addCookies()` in `beforeEach` avoids re-running the login UI for every test. Tests that assert the login flow itself should clear cookies first: `await context.clearCookies()`.

**Visual regression baselines** — commit the initial `*.png` snapshots in `tests/e2e/__snapshots__/`. On CI, Playwright diffs the current render against the baseline. Use `--update-snapshots` to regenerate baselines after intentional UI changes.

**R2 artifact storage** — Playwright HTML reports can be large (screenshots + traces). Storing them in R2 (via the `uploadArtifactsToR2` helper) keeps CI artifact storage lean and provides a permanent URL for debugging flaky tests months later.

## Anti-patterns

- **Asserting on `page.waitForTimeout(2000)`** — fixed sleeps make tests slow and flaky. Use `expect(locator).toBeVisible()` or `page.waitForResponse()` to gate on observable state.
- **Shared browser context across tests** — state leak between tests (logged-in user from test A visible in test B) causes false passes. Use `test.beforeEach` with a fresh context or isolate with `test.use({ storageState: undefined })`.
- **Testing the Worker in isolation via `fetch` inside Playwright tests** — Playwright tests should drive the browser; use Vitest for API-level assertions. Mixing both in one Playwright test obscures what you are actually testing.
- **Skipping global teardown** — leaked `wrangler dev` and Vite processes accumulate across CI runs and consume port 8787. Always kill child processes in `globalTeardown`.

## Gotchas

- `wrangler dev --local` does not support `--env staging` for remote bindings. D1, KV, and Queues run in-memory via Miniflare. Seed data via `/__test/seed` rather than relying on remote state.
- Playwright's `toHaveScreenshot` is OS-specific — screenshots taken on macOS differ from those on Linux due to font rendering. Pin CI to `ubuntu-22.04` and regenerate baselines there.
- The `readFileSync('/tmp/e2e-session.json')` approach is not safe for parallel workers on different machines (e.g. k8s-based CI). Use `process.env` or a shared temp directory on the same runner instead.
- Playwright browser binaries are not included in a standard Node install. Run `npx playwright install --with-deps chromium` in CI before the test step.

## Verification

```bash
# Install browsers
npx playwright install --with-deps chromium

# Run all E2E tests against local dev servers
npx playwright test

# Run a single spec in headed mode for debugging
npx playwright test tests/e2e/checkout.spec.ts --headed --project chromium

# Update visual regression baselines
npx playwright test --update-snapshots

# Show the HTML report
npx playwright show-report
```

## Related

- `documentation/docs/policies/testing/workers-contract-testing-pact.md`
- `documentation/docs/policies/testing/workers-golden-path-test-suite.md`
- Playwright docs: https://playwright.dev/docs/intro
- `wrangler dev` local mode: https://developers.cloudflare.com/workers/wrangler/commands/#dev
- Cloudflare R2 API: https://developers.cloudflare.com/r2/api/s3/api/

## Sources

- Playwright — Test Configuration docs (2025)
- Cloudflare Workers — Local Development guide (2025)
- example.com internal runbook: e2e-testing-playwright (2026-07)
