# Playwright Synthetic Monitoring with Scheduled Runs

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your E2E suite runs on every pull request, but you have no signal between deployments. A database migration lands on Friday evening, silently breaks the checkout flow, and you discover it from customer complaints on Monday morning. You need continuous, production-facing verification of critical paths — separate from your development test suite — that runs on a schedule and alerts when real users would be affected.

Synthetic monitoring bridges the gap between deploy-time confidence and runtime reality.

## Context

Synthetic monitoring means running scripted user journeys against your live environment on a recurring schedule. Playwright is well-suited to this because:

- It ships as a standalone Node.js package (`@playwright/test`) with no browser install friction in CI.
- `playwright.config.ts` supports multiple projects, so you can share test code between your regular suite and your monitoring suite with different base URLs and timeouts.
- GitHub Actions, Cloudflare Workers Cron Triggers, and purpose-built platforms (Checkly, Grafana k6 Browser, Vercel Monitoring) can all host scheduled Playwright runs.
- Trace files, screenshots, and HAR captures give you reproducible forensic evidence when a synthetic check fails at 3 AM.

Synthetic tests differ from development E2E tests in several ways:

| Concern | Dev E2E | Synthetic Monitor |
|---|---|---|
| Target | Staging / preview | Production or canary |
| Frequency | Per commit | Every N minutes |
| Scope | Full regression | Critical happy paths only |
| Data | Seeded fixtures | Dedicated test accounts |
| Alert | PR block | PagerDuty / Slack |
| Teardown | Fixture rollback | Hard delete or no-op accounts |

## Setting Up a Playwright Monitoring Project

### Directory Structure

```
monitoring/
  playwright.config.ts
  checks/
    checkout.spec.ts
    login.spec.ts
    search.spec.ts
  fixtures/
    test-accounts.ts
  .env.monitoring          # NOT committed — injected by CI secrets
```

Separate this from `tests/` entirely. Different lifecycle, different secrets, different failure owners.

### playwright.config.ts for Monitoring

```typescript
// monitoring/playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './checks',
  // Synthetic checks run serially — easier to debug failures
  workers: 1,
  // Retry once to rule out transient network blips
  retries: 1,
  // Longer timeouts: production can be slower than staging
  timeout: 45_000,
  expect: { timeout: 15_000 },
  reporter: [
    ['list'],
    // JUnit for CI artifact ingestion
    ['junit', { outputFile: 'results/monitoring-results.xml' }],
    // HTML report with traces, screenshots, and videos
    ['html', { outputFolder: 'results/html', open: 'never' }],
  ],
  use: {
    baseURL: process.env.MONITORING_BASE_URL ?? 'https://app.example.com',
    // Always capture on failure
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    // Emulate a real browser profile — no headless-only quirks
    ...devices['Desktop Chrome'],
    // Add a recognizable UA so ops can filter synthetic traffic in logs
    userAgent:
      'Mozilla/5.0 (synthetic-monitor; example-org/example-repo) AppleWebKit/537.36',
  },
  projects: [
    { name: 'chromium-prod', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-prod', use: { ...devices['Pixel 7'] } },
  ],
});
```

### Test Account Fixture

```typescript
// monitoring/fixtures/test-accounts.ts
import { test as base } from '@playwright/test';

type MonitoringFixtures = {
  testUser: { email: string; password: string };
};

export const test = base.extend<MonitoringFixtures>({
  testUser: async ({}, use) => {
    // Dedicated synthetic-user accounts that never hold real orders
    const email = process.env.SYNTHETIC_USER_EMAIL;
    const password = process.env.SYNTHETIC_USER_PASSWORD;
    if (!email || !password) {
      throw new Error('Synthetic user credentials not configured');
    }
    await use({ email, password });
    // No teardown: the account is permanent, orders get cleaned by a
    // nightly job that deletes orders placed by synthetic accounts.
  },
});

export { expect } from '@playwright/test';
```

### A Critical Path Check

```typescript
// monitoring/checks/checkout.spec.ts
import { test, expect } from '../fixtures/test-accounts';

test.describe('checkout critical path', () => {
  test('guest can add item and reach payment page', async ({ page }) => {
    await page.goto('/');

    // Search for a known-always-in-stock SKU
    await page.getByRole('searchbox', { name: 'Search products' }).fill('SYNTH-SKU-001');
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Test Product Alpha' })).toBeVisible();

    await page.getByRole('button', { name: 'Add to cart' }).click();
    await expect(page.getByRole('status', { name: 'Cart count' })).toHaveText('1');

    await page.getByRole('link', { name: 'Cart' }).click();
    await page.getByRole('button', { name: 'Proceed to checkout' }).click();

    // Assert payment provider iframe loads — not that we complete payment
    await expect(page.frameLocator('[data-testid="payment-frame"]').getByText('Card number')).toBeVisible();
  });

  test('authenticated user can view order history', async ({ page, testUser }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(testUser.email);
    await page.getByLabel('Password').fill(testUser.password);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page).toHaveURL('/dashboard');
    await page.getByRole('link', { name: 'Orders' }).click();
    // The page must load — content varies so assert the heading
    await expect(page.getByRole('heading', { name: 'Your orders' })).toBeVisible();
  });
});
```

## Scheduling on GitHub Actions

```yaml
# .github/workflows/synthetic-monitoring.yml
name: Synthetic Monitoring

on:
  schedule:
    # Every 15 minutes, around the clock
    - cron: '*/15 * * * *'
  # Allow manual trigger from the Actions UI
  workflow_dispatch:

jobs:
  monitor:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci --prefix monitoring
      - name: Install Playwright browsers
        run: npx playwright install chromium --with-deps
        working-directory: monitoring
      - name: Run synthetic checks
        env:
          MONITORING_BASE_URL: ${{ secrets.PROD_BASE_URL }}
          SYNTHETIC_USER_EMAIL: ${{ secrets.SYNTHETIC_USER_EMAIL }}
          SYNTHETIC_USER_PASSWORD: ${{ secrets.SYNTHETIC_USER_PASSWORD }}
        run: npx playwright test
        working-directory: monitoring

      - name: Upload results on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: monitoring-failure-${{ github.run_id }}
          path: monitoring/results/
          retention-days: 7

      - name: Notify Slack on failure
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": ":red_circle: Synthetic monitoring FAILED on production",
              "attachments": [{
                "text": "Run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
              }]
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_OPS_WEBHOOK }}
```

## Alerting and Trace-Based Debugging

When a check fails, Playwright writes a `.zip` trace archive to `results/`. Download it and open it with:

```bash
npx playwright show-trace monitoring/results/html/trace.zip
```

The trace viewer shows a full DOM snapshot at every action, network waterfall, console errors, and the exact selector that timed out. For production-only failures this is often the only way to reproduce the issue without customer-visible impact.

### Emitting Metrics to Datadog (optional)

```typescript
// monitoring/checks/homepage.spec.ts
test('homepage TTFB under 800 ms', async ({ page }) => {
  const start = Date.now();
  const response = await page.goto('/');
  const ttfb = Date.now() - start;

  // Playwright doesn't expose TTFB natively; use navigation timing instead
  const timing = await page.evaluate(() =>
    JSON.stringify(performance.getEntriesByType('navigation')[0])
  );
  const nav = JSON.parse(timing) as PerformanceNavigationTiming;
  const ttfbMs = nav.responseStart - nav.requestStart;

  // Ship metric — Datadog agent or HTTP API
  if (process.env.DD_API_KEY) {
    await fetch(`https://api.datadoghq.com/api/v1/series`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'DD-API-KEY': process.env.DD_API_KEY,
      },
      body: JSON.stringify({
        series: [{ metric: 'synthetic.ttfb_ms', points: [[Date.now() / 1000, ttfbMs]], tags: ['env:prod'] }],
      }),
    });
  }

  expect(ttfbMs).toBeLessThan(800);
});
```

## Anti-patterns

- **Reusing dev-suite test accounts** — synthetic monitors run continuously; seeded fixture accounts get drained, orders accumulate, and the test state diverges from what dev fixtures expect. Maintain a separate pool of dedicated monitoring accounts.
- **Asserting exact dynamic content** — "Welcome back, John" fails when the name field is updated. Assert structural elements (headings, navigation, form presence) not copy.
- **No retry on the schedule** — a single transient TLS hiccup fires a PagerDuty alert at 2 AM. Set `retries: 1` in the monitoring config and require two consecutive failures before paging.
- **Running too many checks too frequently** — 50 full E2E flows every minute creates non-trivial load on production databases and external payment sandboxes. Keep the monitoring suite to 5–10 critical paths; run at 15-minute intervals.
- **Sharing the monitoring config with the dev suite** — different timeouts, different base URLs, different reporters. They must be separate configs.

## Gotchas

- **CAPTCHA and bot detection** — payment providers and login pages often enable bot protection in production but not staging. Add your synthetic IP range to the allow-list, or use a service token to bypass Turnstile/reCAPTCHA for the synthetic user.
- **Cookie banners** — GDPR consent modals block interactions. Add a `beforeEach` global setup that dismisses the banner, or use a cookie to pre-accept consent via `storageState`.
- **GitHub Actions cron reliability** — scheduled workflows can be delayed by up to 60 minutes during GitHub infrastructure issues. For sub-10-minute SLOs, host your monitors on a dedicated platform (Checkly, Grafana Cloud) instead of GitHub Actions cron.
- **Synthetic traffic contaminating analytics** — filter out your monitoring user agent from GA4, Mixpanel, and Datadog RUM at the ingestion layer, not post-hoc.
- **Production side effects** — some actions (placing an order, sending an email) have real consequences. Use sandbox modes, test-mode flags, or no-op endpoints specifically for synthetic traffic.

## Verification

```bash
# Run locally against staging first
MONITORING_BASE_URL=https://staging.example.com \
SYNTHETIC_USER_EMAIL=synthetic@example.com \
SYNTHETIC_USER_PASSWORD=s3cr3t \
npx playwright test --project=chromium-prod

# Confirm the schedule triggers as expected
gh workflow run synthetic-monitoring.yml --ref main

# Check last 10 scheduled runs
gh run list --workflow=synthetic-monitoring.yml --limit 10
```

Confirm you see:
- All checks green on a known-good production deployment
- A red run with a trace artifact uploaded when you temporarily break a feature flag
- A Slack notification fires within 2 minutes of a failure
- The synthetic user agent appears in your application logs, not in customer analytics dashboards

## Related

- `playwright-e2e-testing-architecture-practices.md`
- `playwright-authentication-state.md`
- `playwright-cloudflare-pages-e2e.md`
- `playwright-trace-retention-and-sensitive-evidence.md`
- `playwright-fail-on-flaky-tests-gate.md`
- `performance-regression-gates-ci.md`

## Sources

- Playwright documentation — `defineConfig` and `projects`: https://playwright.dev/docs/test-configuration
- Playwright Trace Viewer: https://playwright.dev/docs/trace-viewer
- GitHub Actions scheduled workflows: https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule
- Checkly Playwright integration: https://www.checklyhq.com/docs/browser-checks/playwright-test/
- Grafana k6 Browser for synthetic monitoring: https://grafana.com/docs/k6/latest/using-k6-browser/
