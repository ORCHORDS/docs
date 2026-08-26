# Synthetic monitoring with Playwright and uptime checks

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Users report the checkout flow was broken for 40 minutes before
anyone noticed. Uptime checks on the root URL showed HTTP 200 the
entire time — the server was up, but a JavaScript bundle error
silently broke the payment step. HTTP-only probes cannot catch
client-rendered failures.

## Context

Synthetic monitoring runs scripted tests against production on a
schedule, independent of real traffic. It divides into two tiers:
**uptime checks** (HTTP probes that assert status code and optional
body pattern, suitable for API endpoints) and **functional checks**
(full browser automation that exercises a real user journey end-
to-end). Playwright is the standard for functional checks in 2026
because it supports Chromium/Firefox/WebKit and has first-class
network interception. Cloudflare's Browser Rendering API extends
Playwright execution to edge PoPs without self-managed runner VMs.

## Uptime checks vs functional checks

| Dimension          | Uptime check          | Functional check       |
|--------------------|-----------------------|------------------------|
| What it tests      | HTTP reachability     | Real user journey      |
| Failure signal     | Status code / body    | Assertion / screenshot |
| JS execution       | No                    | Yes (full browser)     |
| Typical frequency  | Every 1 min           | Every 5–15 min         |
| Catches JS errors  | No                    | Yes                    |

Run uptime checks every minute for all public API endpoints. Reserve
Playwright checks for the three to five journeys most directly tied
to revenue: login, sign-up, primary CRUD action, checkout.

## Playwright functional check structure

```typescript
// checks/checkout.spec.ts
import { test, expect } from '@playwright/test';

test('checkout flow completes', async ({ page }) => {
  await page.goto('https://example.com/shop');
  await page.getByRole('button', { name: 'Add to cart' }).click();
  await expect(page.getByTestId('cart-count')).toHaveText('1');
  await page.getByRole('link', { name: 'Checkout' }).click();
  await page.getByLabel('Email').fill('synth-test@example.com');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByTestId('order-confirmation'))
    .toBeVisible({ timeout: 10_000 });
});
```

```typescript
// playwright.config.ts — tag synthetic traffic for filtering
export default {
  use: {
    extraHTTPHeaders: { 'X-Synthetic': '1' },
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  retries: 1,
  timeout: 30_000,
};
```

Keep synthetic test accounts isolated from real accounts. Synthetic
orders and sign-ups must be excluded from business analytics.

## Cloudflare Browser Rendering API for edge synthetics

Cloudflare's Browser Rendering API lets a scheduled Worker spin up
headless Chromium at the edge, capturing screenshots or asserting
page state without self-managed runner infrastructure.

```typescript
// worker/synthetic-check.ts
import puppeteer from '@cloudflare/puppeteer';
export default {
  async scheduled(_event, env, _ctx) {
    const browser = await puppeteer.launch(env.BROWSER);
    const page = await browser.newPage();
    try {
      await page.goto('https://example.com/login',
        { waitUntil: 'networkidle0' });
      const ok = (await page.title()).includes('Log in');
      env.AE.writeDataPoint({
        blobs: ['login-check', ok ? 'pass' : 'fail'],
        doubles: [ok ? 1 : 0],
        indexes: ['synthetic'],
      });
      if (!ok) {
        const shot = await page.screenshot({ fullPage: true });
        await env.R2.put(
          `screenshots/${Date.now()}-login-fail.png`, shot);
      }
    } finally { await browser.close(); }
  },
} satisfies ExportedHandler<Env>;
```

Edge synthetics catch region-specific failures (routing mis-
configuration, geo-blocked content) that single-region runners miss.

## Screenshot diffing and API health checks

Capture a baseline screenshot after each production deploy. Compare
subsequent checks against it with a pixel-difference threshold:

```typescript
await expect(page).toHaveScreenshot('homepage.png', {
  maxDiffPixelRatio: 0.02,
  animations: 'disabled',
});
```

For JSON APIs, use Prometheus blackbox prober with body validation
rather than a full browser check. Alert when two consecutive probes
fail to avoid single-miss false positives.

## Limits of synthetic vs RUM

Synthetic monitoring cannot replace Real User Monitoring:
- Synthetics miss device diversity, slow networks, and browser
  extension conflicts.
- A synthetic check passes on fast fiber while 4G users time out.
- Synthetics do not capture rage clicks, scroll depth, or
  UX frustration signals.
Use synthetic as the early-warning system and RUM as the ground
truth for actual user experience.

## Anti-patterns

- **Uptime check on the homepage only** — flows break on internal
  endpoints, not the landing page. Check every critical API path.
- **No X-Synthetic header** — synthetic traffic inflates conversion
  rates and distorts A/B test results.
- **15-minute check intervals** — a 15-minute interval means up to
  15 minutes of undetected downtime on critical paths.
- **Ignoring flaky checks** — a check that fails 1 in 10 runs is a
  broken check. Fix flakiness with explicit waits.

## Gotchas

- `networkidle0` never settles for pages with long-polling or SSE
  connections. Use `load` or `domcontentloaded` instead.
- Cloudflare Browser Rendering has a concurrent browser limit per
  account; queue checks via a Durable Object for parallelism.
- Screenshot diffs fail if the browser renders fonts differently
  across OS versions. Pin the Playwright browser version in CI.
- Synthetic accounts that trigger real emails or SMS must be
  filtered at the provider layer, not just the app layer.

## Verification

- All critical user journeys have a Playwright check every 5 min.
- Every API endpoint has a 1-minute uptime probe.
- Synthetic traffic is filtered from analytics by `X-Synthetic`.
- Screenshot baselines are stored and auto-updated on deploy.
- Alerts fire on two consecutive failures, not one.
- Check runners cover at least two geographic regions.

## Related

- `documentation/categories/monitoring/synthetic-monitoring-uptime-checks.md`
- `documentation/categories/monitoring/real-user-monitoring-rum.md`
- `documentation/categories/monitoring/cloudflare-analytics-engine.md`
- `documentation/categories/monitoring/blackbox-monitoring.md`
- `documentation/categories/monitoring/core-web-vitals-monitoring.md`

## Source URLs (verified 2026-08-17)

- Playwright documentation — https://playwright.dev/docs/intro
- Cloudflare Browser Rendering API —
  https://developers.cloudflare.com/browser-rendering/
- Checkly synthetic monitoring guide —
  https://www.checklyhq.com/docs/monitoring/
- Google SRE: Monitoring distributed systems —
  https://sre.google/sre-book/monitoring-distributed-systems/
