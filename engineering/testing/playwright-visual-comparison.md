# playwright-visual-comparison

**Issue:** Catching unintended visual regressions using Playwright screenshot assertions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CSS changes silently break the visual appearance of components. Screenshot diffing catches regressions automatically.

## Pattern / Solution
```ts
import { test, expect } from "@playwright/test";

test("homepage matches snapshot", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveScreenshot("homepage.png", {
    maxDiffPixels: 100,
  });
});

// Element screenshot
test("button states", async ({ page }) => {
  await page.goto("/components/button");
  const button = page.getByRole("button", { name: "Primary" });
  await expect(button).toHaveScreenshot("button-default.png");

  await button.hover();
  await expect(button).toHaveScreenshot("button-hover.png");
});
```

Update snapshots: `npx playwright test --update-snapshots`

Snapshots stored in `e2e/__screenshots__/` — commit to git.

## Gotchas
- Screenshots vary by OS/browser — generate on the same OS as CI
- Use Docker to ensure consistent rendering across environments
- `maxDiffPixels` prevents false failures from anti-aliasing differences

## Related
- `visual-regression-testing-percy.md`
- `screenshot-testing-patterns.md`
