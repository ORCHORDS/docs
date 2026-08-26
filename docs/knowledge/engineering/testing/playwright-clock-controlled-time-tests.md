# Playwright controlled-time tests

**Issue:** Browser tests wait for real timers or use incomplete time mocks, making expiry, polling, inactivity, and scheduled UI behavior slow and flaky.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

Use Playwright Clock for browser-time behavior. Use `setFixedTime` when only displayed time matters; use `install` before navigation or any clock-related call when timers and `Date.now()` must advance consistently.

**Source:** [Playwright Clock](https://playwright.dev/docs/clock)

## Pattern

```ts
await page.clock.install({ time: new Date("2026-08-12T08:00:00Z") });
await page.goto("/session");
await page.getByRole("button", { name: "Start" }).click();
await page.clock.fastForward("05:00");
await expect(page.getByText("Session expired")).toBeVisible();
```

## Verification

- test fixed display dates separately from timer-driven expiry;
- install the clock before page code can create timers;
- assert the user-visible state and the network/storage consequence;
- cover a refresh or new context when the feature persists timestamps;
- retain one real-browser-time smoke test for integration assumptions.

## Gotchas

- Clock controls the whole BrowserContext, including pages and iframes.
- `fastForward` fires due timers at most once; use `runFor` when every timer callback matters.
- Installing after time APIs have been used gives undefined behavior.
- Do not use fixed time to hide timezone/DST defects; test those with explicit zones separately.

## Related

- `testing/timezone-dst-boundary-regression-tests.md`
- `testing/playwright-har-replay-fixture-governance.md`
