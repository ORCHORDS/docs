# visual-regression-testing-percy

**Issue:** Detecting unintended UI changes through pixel-level screenshot comparison
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CSS refactors and dependency upgrades silently break visual layout. Functional tests still pass because behaviour is unchanged, but the UI looks wrong.

## Pattern / Solution
Percy captures screenshots during test runs and compares them to the baseline approved in the Percy dashboard:

**With Playwright:**
```ts
import percySnapshot from "@percy/playwright";

test("checkout page renders correctly", async ({ page }) => {
  await page.goto("/checkout");
  await percySnapshot(page, "Checkout Page");
});
```

**With Storybook:**
```bash
percy storybook ./storybook-static
```

Set `PERCY_TOKEN` in CI secrets. Percy uploads screenshots to its cloud service and opens a visual diff review in the PR.

Approve baseline screenshots once on a feature branch; subsequent runs compare against those approved baselines.

## Gotchas
- Dynamic content (timestamps, animated GIFs, user avatars) causes false positives — hide or freeze these before capturing.
- Percy screenshots are taken at a fixed viewport; test multiple breakpoints explicitly.
- Free tier has a screenshot limit; use selective snapshotting on the most critical pages.

## Related
- playwright-visual-comparison
- screenshot-testing-patterns
- component-testing-storybook
