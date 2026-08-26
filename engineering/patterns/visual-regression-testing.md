# visual-regression-testing

**Issue:** Catch unintended visual changes with Playwright snapshots
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a CSS change. The homepage looks the same. But the
settings page has a layout bug — the button is now overlapping
the user dropdown. No one noticed in code review. The bug ships.

## Root cause
**Visual regressions are hard to catch in unit tests.** A unit
test checks "the component renders." It doesn't check "the
component looks the same as before."

**Source:** Playwright visual comparisons:
https://playwright.dev/docs/test-snapshots

> "Visual comparisons detect unintended visual changes ... by
> comparing pixel-level differences."

## The pattern: snapshot testing

### Take a snapshot
```ts
import { test, expect } from '@playwright/test';

test('homepage visual snapshot', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveScreenshot('homepage.png', {
    maxDiffPixels: 100,  // allow tiny rendering differences
  });
});
```

### Update the snapshot when the change is intentional
```bash
npx playwright test --update-snapshots
# Updates homepage.png to the current render
```

### The CI flow
1. Push to PR #<number>. CI runs the visual tests
3. If the snapshot diff is large, the test fails
4. Reviewer examines the diff
5. If intentional, update the snapshot
6. If unintentional, fix the code

## The diff visualization

When the snapshot fails, Playwright shows a visual diff:
- **Pink:** pixels that changed
- **Yellow:** pixels that are new
- **No color:** unchanged pixels

This makes it easy to see WHAT changed, not just THAT
something changed.

## Per-locale snapshots

For a multi-locale app, take a snapshot per locale:
```ts
for (const locale of ['en', 'zh-CN', 'ar-SA', 'ja', 'ru']) {
  test(`homepage ${locale}`, async ({ page }) => {
    await page.goto(`http://localhost:3000/${locale}`);
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveScreenshot(`homepage-${locale}.png`);
  });
}
```

A translation that overflows the layout in `ar-SA` (RTL) is
caught by this.

## What to snapshot

✅ Snapshot:
- **Homepage** (the most-trafficked page)
- **Critical user paths** (signup, login, checkout, settings)
- **Empty states** (no data, no notifications)
- **Error states** (404, 500, network error)
- **Loading states** (skeleton screens, progress bars)
- **Modal overlays** (delete confirmation, photo upload)
- **Per-locale** (if i18n)

❌ Don't snapshot:
- **Pages that change frequently** (dashboards with live
  data) — too many false positives
- **Animations** (Playwright captures the animation frame, not
  the final state)
- **Pages with timestamps** (every render is different)

## Anti-patterns

### Snapshots of dynamic content
If the page has a "current time" widget, the snapshot will
fail every time the test runs. Use a `Date.now()` mock or
exclude the dynamic area:
```ts
await expect(page).toHaveScreenshot('homepage.png', {
  mask: [page.locator('.timestamp')],  // mask this region
});
```

### Snapshot of the entire page when only a region changed
If only a button changed, you don't need a full-page snapshot:
```ts
await expect(page.locator('.header')).toHaveScreenshot('header.png');
```

### Updates without review
The "update snapshot" command should be intentional, not
reflexive. Always review the diff before updating.

## The "visual QA" vs "visual regression" distinction

- **Visual regression testing:** automated, in CI, catches
  changes the dev didn't intend
- **Visual QA:** manual, by a human, catches issues that
  automation can't (a11y, design taste, etc.)

Both are useful. Visual regression catches the bugs. Visual QA
catches the design issues.

## Verification
- **Test:** Visual tests pass on the current main
- **Live:** PRs with visual diffs are flagged for review
- **Audit:** Quarterly review of snapshot size + false
  positive rate

## Gotchas
- **Cross-browser differences** cause false positives. The
  same page may render differently in Chrome vs Firefox.
  Pick one browser for snapshot tests (usually Chromium).
- **Cross-platform font rendering** is different. macOS
  renders fonts slightly differently than Linux. Use a
  consistent test environment (Linux + Chromium).
- **The first run** doesn't have a snapshot; Playwright
  creates one. The first run always passes (which is the
  point — you commit the baseline).
- **A large diff doesn't always mean a bug.** Sometimes a
  redesign is intentional. The test passes once you update
  the snapshot.
- **Snapshot tests are slow.** Visual tests can take
  10-30 seconds each. Don't snapshot every page; snapshot
  the critical ones.

## Related
- `accessibility-wcag.md` (visual testing complements a11y)
- `i18n/rtl-safe-component-patterns.md` (RTL visual tests)
- Playwright: https://playwright.dev/docs/test-snapshots
- Chromatic: https://www.chromatic.com/
