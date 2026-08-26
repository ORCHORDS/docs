# screenshot-testing-patterns

**Issue:** Capturing and comparing screenshots reliably without excessive false positives
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Screenshot tests fail on every run due to minor rendering differences between OS font engines, GPU rendering, and sub-pixel anti-aliasing.

## Pattern / Solution
Use Playwright's built-in screenshot comparison with a tolerance threshold:

```ts
await expect(page).toHaveScreenshot("dashboard.png", {
  maxDiffPixels: 100,          // allow minor rendering variation
  threshold: 0.1,              // per-pixel colour difference tolerance
  animations: "disabled",      // freeze CSS animations
  mask: [page.locator(".timestamp")], // mask dynamic regions
});
```

Organise screenshot baselines by OS and browser to avoid cross-platform diffs:

```
__snapshots__/
  linux-chromium/
    dashboard.png
  darwin-chromium/
    dashboard.png
```

Update baselines intentionally with `--update-snapshots`; commit the new files in a dedicated PR with a visual review checklist.

## Gotchas
- Never run screenshot tests in headed mode for CI — headless renders differently.
- Font rendering on Windows differs from Linux CI — pin a Docker image for consistent baselines.
- Lazy-loaded images must be fully loaded before the screenshot is taken; wait for `networkidle` or specific image locators.

## Related
- playwright-visual-comparison
- visual-regression-testing-percy
- snapshot-testing-pitfalls
