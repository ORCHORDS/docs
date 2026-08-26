# playwright-mobile-device-emulation

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

E2E tests pass in CI but the product team reports broken
layouts and inaccessibly small tap targets on real phones.
No mobile coverage exists in the test suite.

## Context

Playwright ships a `devices` registry that bundles the User-
Agent string, viewport, device pixel ratio, and touch
support needed to emulate phones and tablets inside a
headless Chromium, Firefox, or WebKit process. Emulation is
cheap, parallelisable, and sufficient for layout and
interaction regressions. Real-device grids (Sauce Labs,
BrowserStack) remain necessary for GPU-dependent rendering,
hardware APIs, and final release sign-off.

## Device Presets and Viewport Configuration

`devices['iPhone 15']` is the most common iOS preset:

```ts
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  projects: [
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 7'] },
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 15'] },
    },
  ],
});
```

Properties injected by the spread for `iPhone 15`:

| Property            | Value                        |
|---------------------|------------------------------|
| `viewport`          | `{ width: 393, height: 852 }`|
| `deviceScaleFactor` | `3`                          |
| `isMobile`          | `true`                       |
| `hasTouch`          | `true`                       |
| `defaultBrowserType`| `webkit`                     |

Override individual keys after the spread:

```ts
use: {
  ...devices['iPhone 15'],
  viewport: { width: 320, height: 568 }, // SE size
},
```

## Network Throttling

Playwright exposes Chrome DevTools Protocol (CDP) network
emulation in Chromium projects only:

```ts
test('loads under 3G', async ({ page, context }) => {
  const cdp = await context.newCDPSession(page);
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false,
    downloadThroughput: (750 * 1024) / 8, // 750 Kbps
    uploadThroughput:   (250 * 1024) / 8, // 250 Kbps
    latency: 100,                          // ms RTT
  });
  await page.goto('/');
  await expect(page.getByRole('main')).toBeVisible();
});
```

Preset reference:

| Profile | Down      | Up        | RTT    |
|---------|-----------|-----------|--------|
| 3G slow | 750 Kbps  | 250 Kbps  | 100 ms |
| 4G LTE  | 4 Mbps    | 3 Mbps    | 20 ms  |
| Cable   | 5 Mbps    | 1 Mbps    | 14 ms  |

For WebKit projects use a proxy-level tool such as
`toxiproxy` to simulate link degradation.

## Geolocation, Locale, and Dark Mode

```ts
test('checkout shows EUR in France', async ({ browser }) => {
  const ctx = await browser.newContext({
    geolocation: { latitude: 48.8566, longitude: 2.3522 },
    permissions:  ['geolocation'],
    colorScheme:  'dark',       // prefers-color-scheme: dark
    locale:       'fr-FR',
    timezoneId:   'Europe/Paris',
  });
  const page = await ctx.newPage();
  await page.goto('/checkout');
  await expect(
    page.getByTestId('currency')
  ).toHaveText('€');
  await ctx.close();
});
```

`colorScheme` toggles `prefers-color-scheme` only; it does
not change the OS chrome or system font rendering.

## Emulation vs Real-Device Testing

Emulation gaps that require escalation to real hardware:

- CSS `hover` fires on mouse move even with `isMobile:
  true`; real phones never trigger it.
- WebKit on Linux renders fonts differently from Safari on
  iOS — visual snapshots drift.
- Hardware-accelerated video codecs, NFC, biometrics, and
  push notifications are unavailable.
- Battery, gyroscope, and accelerometer return stubs.

When to use Sauce Labs or BrowserStack:
- Pre-release gate for flagship versions
- App-store submission validation
- Bugs reproducible only on specific OS firmware
- Camera / microphone / background-sync workflows

Both grids accept unmodified Playwright scripts via CDP
`connect`:

```ts
const browser = await chromium.connect(
  `wss://cdp.browserstack.com/playwright?caps=${caps}`
);
```

## Anti-patterns

- Taking pixel-perfect snapshots against WebKit on Linux
  and treating diffs as regressions — font hinting varies
  by OS.
- Applying CDP throttling to WebKit or Firefox projects —
  the call silently fails or throws.
- Sharing a `BrowserContext` across tests — geolocation,
  permissions, and cookies leak between runs.
- Using `isMobile` as a feature-detection proxy in app
  code — detect capabilities directly (`ontouchstart`).

## Gotchas

- `devices` keys are case-sensitive: `'iPhone 15'` not
  `'iphone-15'`. Enumerate all keys with
  `Object.keys(devices)`.
- `hasTouch: true` enables single taps via
  `page.touchscreen.tap()`; multi-touch gestures require
  custom pointer events.
- Geolocation permission must be granted at context
  creation; the browser throws `GeolocationPositionError`
  if the app calls the API before permission is granted.
- `deviceScaleFactor` sets `window.devicePixelRatio` but
  does not enlarge screenshot dimensions automatically.

## Verification

```bash
# Run only the mobile-safari project
npx playwright test --project=mobile-safari

# List all shipped device presets
node -p "Object.keys(require('@playwright/test').devices)"
```

A 20-test mobile suite using `iPhone 15` completes in
under 90 s on a standard 2-core CI runner.

## Related

- `testing/playwright-setup.md`
- `testing/cross-browser-testing.md`
- `testing/mobile-browser-testing.md`
- `testing/playwright-network-interception.md`
- `testing/playwright-visual-comparison.md`

## Source URLs (verified 2026-08-17)

- https://playwright.dev/docs/emulation
- https://playwright.dev/docs/api/class-browser#browser-new-context
- https://chromedevtools.github.io/devtools-protocol/tot/Network/#method-emulateNetworkConditions
- https://www.browserstack.com/docs/automate/playwright/getting-started
- https://docs.saucelabs.com/web-apps/automated-testing/playwright/
