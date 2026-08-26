# cross-browser-testing

**Issue:** Verifying that web features work correctly across Chrome, Firefox, and Safari
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A feature works in Chrome but breaks in Safari due to a CSS property or Web API difference, discovered by a user rather than in testing.

## Pattern / Solution
Playwright supports multi-browser execution natively:

```ts
// playwright.config.ts
projects: [
  { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  { name: "firefox",  use: { ...devices["Desktop Firefox"] } },
  { name: "webkit",   use: { ...devices["Desktop Safari"] } },
],
```

Run the full E2E suite against all three in CI. For unit/component tests, browser differences rarely matter — focus cross-browser effort on E2E critical paths.

For features using experimental APIs, check caniuse data and add polyfill tests:

```ts
test.describe("IntersectionObserver polyfill", () => {
  test.use({ browserName: "webkit" });
  test("loads polyfill in Safari", async ({ page }) => { ... });
});
```

## Gotchas
- WebKit (Safari engine) on Linux in CI is not identical to Safari on macOS — visual differences may still appear.
- Playwright downloads browser binaries for each version; cache them in CI to avoid slow installs.
- Run cross-browser tests on a schedule (nightly) rather than every PR to keep PR pipelines fast.

## Related
- playwright-setup
- playwright-parallel-execution
- mobile-browser-testing
