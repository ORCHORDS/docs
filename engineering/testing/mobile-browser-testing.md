# mobile-browser-testing

**Issue:** Testing web applications at mobile viewport sizes and with touch interactions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The desktop experience is fully tested but mobile layouts break or touch targets are too small, discovered only after release.

## Pattern / Solution
Playwright device emulation covers viewport, user-agent, and touch events:

```ts
import { devices } from "@playwright/test";

// playwright.config.ts
projects: [
  { name: "mobile-chrome",  use: { ...devices["Pixel 7"] } },
  { name: "mobile-safari",  use: { ...devices["iPhone 15"] } },
],
```

For specific tests:
```ts
test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

test("hamburger menu opens on tap", async ({ page }) => {
  await page.goto("/");
  await page.tap("[data-testid='menu-toggle']");
  await expect(page.locator("nav")).toBeVisible();
});
```

Test responsive breakpoints by resizing the viewport within a single test to verify layout switches.

## Gotchas
- Emulation is not a substitute for real-device testing for gesture-heavy features (swipe carousels, pinch-zoom).
- Mobile Safari (WebKit on iOS) is only accurately emulated on macOS — Linux CI uses WebKit but without the iOS-specific quirks.
- Test touch target sizes: WCAG recommends a minimum 44×44 CSS pixels for interactive elements.

## Related
- cross-browser-testing
- playwright-setup
- a11y-automated-testing-axe
