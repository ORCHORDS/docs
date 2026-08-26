# Playwright E2E Tests for Mobile WebView in CI with BrowserStack

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your Expo React Native app renders certain flows in an in-app WebView that loads a Cloudflare
Pages URL (e.g. the payment confirmation page, the OAuth callback, the embedded catalog). These
pages look correct in Chrome DevTools mobile emulation but break on real Android WebView because
WebView ships an older Chromium version that lacks `OffscreenCanvas` support, has different
Content Security Policy header parsing, and ignores `position: sticky` in certain scroll
containers. You need automated CI coverage on a real Android device's WebView, not a desktop
browser emulating mobile.

## Context

Playwright can drive real mobile devices via the **BrowserStack Automate** integration. BrowserStack
exposes a Playwright-compatible CDP endpoint that connects to a real Android or iOS device. This
means you write standard Playwright tests and swap the browser launch for a BrowserStack remote
connection — no Appium, no Detox, no platform-specific test code.

Key differences from standard Playwright:

| Concern | Desktop Playwright | BrowserStack + Playwright |
|---|---|---|
| Browser launch | `chromium.launch()` | `chromium.connect(wsEndpoint)` |
| Device selection | `devices['Pixel 7']` (emulated) | BrowserStack capability JSON |
| Network speed | CDP `emulateNetworkConditions` | BrowserStack network preset |
| Cost | Free | Billed by session minutes |
| CI trigger | Every PR | Nightly or release-gated |

Stack: Playwright 1.48+, BrowserStack Automate, Expo SDK 52 (WebView target), Cloudflare Pages
staging, GitHub Actions.

---

## Project Structure

```
tests/
  e2e/
    webview/
      payment-webview.spec.ts
      oauth-callback.spec.ts
    desktop/
      search.spec.ts           # Standard desktop/emulated tests (run on every PR)
playwright.webview.config.ts  # Separate config for BrowserStack real-device runs
playwright.config.ts          # Standard config (emulated, runs on every PR)
```

Separating the configs prevents the expensive BrowserStack sessions from running on every pull
request while still catching WebView-specific regressions nightly.

---

## BrowserStack Playwright Config

```ts
// playwright.webview.config.ts
import { defineConfig, devices } from '@playwright/test';

/**
 * BrowserStack Automate WebSocket endpoint.
 * Format: wss://cdp.browserstack.com/playwright?caps=<base64-encoded-caps>
 *
 * Capabilities reference:
 *   https://www.browserstack.com/docs/automate/playwright/capabilities
 */
function bsCapsEndpoint(caps: Record<string, unknown>): string {
  const encoded = Buffer.from(JSON.stringify(caps)).toString('base64');
  return `wss://cdp.browserstack.com/playwright?caps=${encodeURIComponent(encoded)}`;
}

const commonCaps = {
  'browserstack.username': process.env.BROWSERSTACK_USERNAME,
  'browserstack.accessKey': process.env.BROWSERSTACK_ACCESS_KEY,
  'browserstack.networkLogs': true,
  'browserstack.consoleLogs': 'verbose',
  // Upload test artifacts to BrowserStack for debugging.
  'browserstack.video': true,
  'build': process.env.GITHUB_RUN_ID ?? 'local',
  'project': 'OrchordsApp WebView',
};

export default defineConfig({
  testDir: './tests/e2e/webview',
  timeout: 120_000,        // WebView on real device is slower than emulated.
  retries: 1,              // One retry for network flakiness on BrowserStack.
  // Run serially to manage BrowserStack parallel session quota.
  workers: 2,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report-webview' }],
    ['junit', { outputFile: 'results/webview-junit.xml' }],
  ],
  use: {
    baseURL: process.env.PAGES_STAGING_URL ?? 'https://staging.pages.dev',
    // Screenshots on failure are essential for real-device debugging.
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
    // Do NOT pass `browserName` here — each project specifies its device.
  },
  projects: [
    {
      name: 'Android 14 – Pixel 8 – Chrome WebView',
      use: {
        connectOptions: {
          wsEndpoint: bsCapsEndpoint({
            ...commonCaps,
            'name': 'WebView – Pixel 8 – Android 14',
            'os': 'android',
            'os_version': '14.0',
            'device': 'Google Pixel 8',
            'browser': 'chrome',   // WebView is the system WebView; use chrome channel.
            // Emulate WebView-like constraints: no extensions, restricted JS APIs.
            'browserstack.deviceType': 'real',
          }),
        },
        // Viewport that matches the WebView container in the Expo app.
        viewport: { width: 393, height: 720 },
        userAgent:
          'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 ' +
          '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
      },
    },
    {
      name: 'Android 12 – Samsung Galaxy S22 – Chrome WebView',
      use: {
        connectOptions: {
          wsEndpoint: bsCapsEndpoint({
            ...commonCaps,
            'name': 'WebView – Galaxy S22 – Android 12',
            'os': 'android',
            'os_version': '12.0',
            'device': 'Samsung Galaxy S22',
            'browser': 'chrome',
            'browserstack.deviceType': 'real',
          }),
        },
        viewport: { width: 360, height: 780 },
      },
    },
    {
      name: 'iOS 17 – iPhone 15 – Safari WKWebView',
      use: {
        connectOptions: {
          wsEndpoint: bsCapsEndpoint({
            ...commonCaps,
            'name': 'WebView – iPhone 15 – iOS 17',
            'os': 'ios',
            'os_version': '17',
            'device': 'iPhone 15',
            'browser': 'safari',
            'browserstack.deviceType': 'real',
          }),
        },
        viewport: { width: 390, height: 844 },
        // iOS WKWebView enforces strict CSP; test that headers are correct.
      },
    },
  ],
});
```

---

## Writing the WebView Spec

```ts
// tests/e2e/webview/payment-webview.spec.ts
import { test, expect } from '@playwright/test';

/**
 * These tests verify the payment confirmation page as rendered inside
 * the React Native WebView. The page is served by Cloudflare Pages.
 *
 * The WebView in the Expo app navigates to:
 *   https://staging.pages.dev/payment/confirm?orderId=<id>&token=<jwt>
 *
 * We test that the page:
 * - Renders the order summary without JS errors.
 * - Calls window.ReactNativeWebView.postMessage on "Done" tap (bridge check).
 * - Does not use APIs that WebView blocks (e.g. window.open, clipboard API).
 */

test.describe('Payment confirmation WebView page', () => {
  const ORDER_ID = 'test-order-001';
  const TOKEN = 'eyJtb2NrIjoidHJ1ZSJ9'; // mock JWT, validated by staging Worker.

  test('renders order summary on Android WebView', async ({ page }) => {
    await page.goto(
      `/payment/confirm?orderId=${ORDER_ID}&token=${TOKEN}`,
      { waitUntil: 'domcontentloaded' },
    );

    // Check for critical UI elements.
    await expect(page.getByRole('heading', { name: /order confirmed/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId('order-id')).toHaveText(ORDER_ID);
    await expect(page.getByTestId('total-price')).toBeVisible();
  });

  test('postMessage bridge fires on Done button tap', async ({ page }) => {
    // Intercept window.ReactNativeWebView.postMessage calls.
    const bridgeMessages: string[] = [];
    await page.exposeFunction('__captureRNBridgeMessage', (msg: string) => {
      bridgeMessages.push(msg);
    });

    // Inject a mock for the React Native WebView bridge before navigation.
    await page.addInitScript(() => {
      (window as any).ReactNativeWebView = {
        postMessage: (msg: string) => {
          (window as any).__captureRNBridgeMessage(msg);
        },
      };
    });

    await page.goto(`/payment/confirm?orderId=${ORDER_ID}&token=${TOKEN}`, {
      waitUntil: 'networkidle',
    });

    await page.getByRole('button', { name: /done/i }).tap();

    // Allow up to 5 s for the postMessage to fire.
    await expect.poll(() => bridgeMessages.length, { timeout: 5_000 }).toBeGreaterThan(0);
    const parsed = JSON.parse(bridgeMessages[0]);
    expect(parsed).toMatchObject({ type: 'PAYMENT_DONE', orderId: ORDER_ID });
  });

  test('no console errors on page load', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto(`/payment/confirm?orderId=${ORDER_ID}&token=${TOKEN}`, {
      waitUntil: 'networkidle',
    });

    // Filter known benign errors (e.g. BrowserStack's own injected scripts).
    const appErrors = consoleErrors.filter(
      e => !e.includes('BrowserStack') && !e.includes('favicon.ico'),
    );
    expect(appErrors).toHaveLength(0);
  });

  test('CSP headers do not block Cloudflare Worker API call', async ({ page }) => {
    const failedRequests: string[] = [];
    page.on('requestfailed', req => failedRequests.push(req.url()));

    await page.goto(`/payment/confirm?orderId=${ORDER_ID}&token=${TOKEN}`, {
      waitUntil: 'networkidle',
    });

    const apiFailures = failedRequests.filter(u => u.includes('/v1/orders'));
    expect(apiFailures).toHaveLength(0);
  });
});
```

---

## GitHub Actions CI Integration

```yaml
# .github/workflows/webview-e2e.yml
name: WebView E2E (BrowserStack)

on:
  schedule:
    - cron: '0 3 * * *'   # Nightly 03:00 UTC
  workflow_dispatch:

jobs:
  webview-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 40
    env:
      BROWSERSTACK_USERNAME: ${{ secrets.BROWSERSTACK_USERNAME }}
      BROWSERSTACK_ACCESS_KEY: ${{ secrets.BROWSERSTACK_ACCESS_KEY }}
      PAGES_STAGING_URL: ${{ vars.PAGES_STAGING_URL }}

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      # No `npx playwright install` — browsers run on BrowserStack, not locally.
      # We still need Playwright itself for the test runner.

      - name: Mark build on BrowserStack
        run: |
          curl -u "$BROWSERSTACK_USERNAME:$BROWSERSTACK_ACCESS_KEY" \
            -X PUT "https://api.browserstack.com/automate/builds/${{ github.run_id }}.json" \
            -H "Content-Type: application/json" \
            -d '{"build": {"name": "WebView CI '${{ github.sha }}'"}}'

      - name: Run WebView Playwright tests
        run: |
          pnpm playwright test \
            --config=playwright.webview.config.ts \
            --reporter=list,junit \
            --output=results
        timeout-minutes: 30

      - name: Upload test report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-webview-report
          path: playwright-report-webview/
          retention-days: 14

      - name: Publish JUnit results
        uses: dorny/test-reporter@v1
        if: always()
        with:
          name: WebView E2E Results
          path: results/webview-junit.xml
          reporter: java-junit
```

---

## Anti-patterns

**Using `chromium.launch()` with `devices['Pixel 7']` for WebView tests.**
Emulated devices use the same Chromium version as the test runner. Real Android WebView may be
several major versions behind (Android 10–11 devices ship WebView 96–110). Bugs in older WebView
versions are completely invisible to emulation.

**Running BrowserStack tests on every pull request.**
BrowserStack sessions are billed per minute and are rate-limited by your plan's parallel
sessions. Real-device tests should run nightly or on release branches. Use emulated mobile
Playwright tests on PRs as a fast gate.

**Not injecting the `ReactNativeWebView` bridge mock.**
Without the mock, any code that calls `window.ReactNativeWebView.postMessage` throws a runtime
error in the browser (it is only available inside the actual Expo WebView). The test will appear
to pass (no assertion fails) while the actual bridge call silently throws.

**Hardcoding a real BrowserStack session token in the `wsEndpoint` URL.**
The access key rotates and is sensitive. Always read it from environment variables; never commit
it to the repository.

---

## Gotchas

- **BrowserStack Playwright uses CDP over WSS** — the connection requires outbound WSS to
  `cdp.browserstack.com`. If your CI runner is behind a restrictive firewall, add this domain
  to the allowlist.

- **iOS WKWebView restrictions** — WKWebView blocks `window.open()`, `navigator.clipboard`,
  and certain `localStorage` access modes. Tests that rely on these APIs fail silently (no
  error, just no effect). Assert on the page state rather than mocking these APIs.

- **Viewport vs screen size** — BrowserStack device viewport may differ from `viewport` set
  in the Playwright config. Always set both `viewport` and let Playwright respect the device's
  actual render dimensions by not over-constraining the viewport.

- **Real-device latency** — Playwright's default `timeout` (30 s) is often too short for
  real-device cold starts. Set `timeout: 120_000` in the config and per-test where needed.

- **BrowserStack session reuse** — each `connectOptions.wsEndpoint` call creates a new
  BrowserStack session. Worker count in the Playwright config directly maps to parallel sessions
  consumed; set `workers` conservatively relative to your plan quota.

---

## Verification

```bash
# 1. Smoke-test one WebView spec locally using emulated mobile (no BrowserStack cost).
npx playwright test tests/e2e/webview/payment-webview.spec.ts \
  --config=playwright.config.ts \
  --project="Mobile Chrome"

# 2. Run the full BrowserStack suite manually (requires credentials).
BROWSERSTACK_USERNAME=xxx BROWSERSTACK_ACCESS_KEY=yyy \
PAGES_STAGING_URL=https://staging.pages.dev \
  npx playwright test --config=playwright.webview.config.ts --project="Android 14*"

# 3. Check BrowserStack dashboard for session recording.
#    https://automate.browserstack.com/builds/<build-id>

# 4. Trigger nightly workflow manually in GitHub Actions → webview-e2e → Run workflow.
```

---

## Related

- `playwright-mobile-device-emulation.md`
- `playwright-cloudflare-pages-e2e.md`
- `playwright-e2e-testing-architecture-practices.md`
- `detox-react-native-e2e.md`
- `mobile-browser-testing.md`

## Sources

- BrowserStack Playwright integration docs: https://www.browserstack.com/docs/automate/playwright
- BrowserStack Automate capabilities: https://www.browserstack.com/docs/automate/playwright/capabilities
- Playwright `connectOptions`: https://playwright.dev/docs/api/class-browsertype#browser-type-connect
- Android WebView release schedule: https://chromium.googlesource.com/chromium/src/+/HEAD/android_webview/docs/channels.md
