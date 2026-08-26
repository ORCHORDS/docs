# Visual Regression Testing

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

CSS changes break unrelated pages and components, but you only discover
the damage after deploying to production. Code review cannot reliably
catch visual regressions — a one-line CSS change can shift layouts across
dozens of pages. Your design system components look correct in Storybook
but render incorrectly when composed in the actual application. Responsive
breakpoints are tested manually, if at all.

## Context

Visual regression testing captures screenshots of UI components or pages
and compares them against approved baselines to detect unintended visual
changes. In 2026, the tool landscape has split into two camps: cloud
platforms with AI-powered diffing (Chromatic, Percy, Applitools) that
reduce false positives through intelligent comparison, and developer-
owned snapshot libraries built into test frameworks (Playwright, Cypress)
that run locally with pixel-level comparison. Cloud platforms report
up to 40% fewer false positives compared to pixel-diff tools, while
framework-native tools are free and fully under your control.

## Tool comparison

| Feature | Chromatic | Percy | Applitools | Playwright |
|---|---|---|---|---|
| Approach | Storybook-native | DOM snapshot | AI visual AI | Pixel screenshot |
| Integration | Storybook | Any framework | Any framework | Playwright tests |
| Diffing | Smart (component-aware) | DOM-based | Visual AI (no false positives claim) | Pixel-level |
| CI integration | GitHub Actions, CI | GitHub Actions, CI | GitHub Actions, CI | Built-in |
| Review workflow | Web UI with approve/reject | Web UI | Web UI | Local assertion |
| Pricing | Per snapshot | Per snapshot | Per checkpoint | Free (OSS) |
| False positive rate | Low | Low-medium | Very low (AI) | Medium-high |

## Playwright visual testing

```typescript
import { test, expect } from '@playwright/test';

test('homepage visual regression', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveScreenshot('homepage.png', {
    maxDiffPixelRatio: 0.01,
  });
});

test('product card component', async ({ page }) => {
  await page.goto('/components/product-card');
  const card = page.locator('[data-testid="product-card"]');
  await expect(card).toHaveScreenshot('product-card.png');
});

test('responsive layouts', async ({ page }) => {
  for (const viewport of [
    { width: 375, height: 812 },   // iPhone
    { width: 768, height: 1024 },  // iPad
    { width: 1440, height: 900 },  // Desktop
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await expect(page).toHaveScreenshot(
      `homepage-${viewport.width}.png`
    );
  }
});
```

### Updating baselines

```bash
# Update all snapshots
npx playwright test --update-snapshots

# Update specific test snapshots
npx playwright test homepage.spec.ts --update-snapshots
```

## Chromatic (Storybook-native)

```typescript
// .storybook/main.ts
export default {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: ['@chromatic-com/storybook'],
};
```

```yaml
# CI integration
- name: Visual regression tests
  run: npx chromatic --project-token=${{ secrets.CHROMATIC_TOKEN }}
```

Chromatic captures every Storybook story as a visual test. TurboSnap
only snapshots stories affected by code changes, reducing cost and
runtime.

## Percy (DOM snapshots)

```typescript
// Cypress + Percy
describe('Dashboard', () => {
  it('renders correctly', () => {
    cy.visit('/dashboard');
    cy.percySnapshot('Dashboard - default');

    cy.get('[data-testid="dark-mode"]').click();
    cy.percySnapshot('Dashboard - dark mode');
  });
});
```

Percy snapshots the DOM rather than taking screenshots, rendering on its
own browsers to produce consistent baselines across environments.

## Reducing false positives

| Technique | How it helps |
|---|---|
| Threshold tolerance | Allow small pixel differences (anti-aliasing, font rendering) |
| Element masking | Ignore dynamic content (timestamps, avatars, ads) |
| Viewport pinning | Fixed viewport size prevents layout shift noise |
| Animation disabling | Disable CSS animations before capture |
| Font loading wait | Wait for web fonts to load before screenshot |
| Stable test data | Use deterministic data, not production data |

```typescript
// Playwright: reducing false positives
test('dashboard', async ({ page }) => {
  await page.goto('/dashboard');

  // Mask dynamic content
  await expect(page).toHaveScreenshot('dashboard.png', {
    mask: [
      page.locator('.timestamp'),
      page.locator('.user-avatar'),
    ],
    maxDiffPixelRatio: 0.005,
    animations: 'disabled',
  });
});
```

## Anti-patterns

- **Screenshot everything** — capturing full-page screenshots of every
  page creates a massive baseline set that is slow to review and
  generates many false positives. Focus on critical components and pages.
- **No review workflow** — visual diffs without a review/approve process
  means baselines are blindly updated, defeating the purpose. Use cloud
  platforms or PR-based review for approvals.
- **Testing against production data** — dynamic content (prices, user
  counts, dates) changes between runs, causing false positives. Use
  stable test data or mock dynamic content.
- **Ignoring CI environment differences** — font rendering, anti-
  aliasing, and sub-pixel rendering differ between macOS and Linux CI
  runners. Run visual tests in Docker or on consistent CI runners.

## Gotchas

- **Font rendering across platforms** — the same font renders
  differently on macOS, Linux, and Windows. Running visual tests in
  Docker with a consistent font stack eliminates cross-platform
  differences.
- **Snapshot storage and versioning** — pixel-level snapshots are binary
  files that bloat Git repositories. Store baselines in LFS, a cloud
  service, or `.gitignore` them and regenerate in CI.
- **Storybook interaction states** — hover, focus, and active states
  require explicit setup in stories. Without interaction testing, visual
  regressions in interactive states go undetected.
- **Flaky screenshots** — animations, lazy loading, and async rendering
  cause non-deterministic screenshots. Use `waitForLoadState`,
  `animations: 'disabled'`, and explicit waits for stability.

## Verification

- Critical pages and components have visual regression tests.
- Baselines are reviewed and approved before updating.
- CI runs visual tests on every PR.
- False positive rate is below 5% of total snapshots.
- Responsive breakpoints are tested (mobile, tablet, desktop).
- Dynamic content is masked or mocked for stable comparisons.

## Related

- `documentation/docs/policies/testing/mobile-app-testing-automation-frameworks.md`
- `documentation/docs/policies/testing/event-driven-async-api-testing.md`
- `documentation/docs/policies/frontend/component-testing.md`

## Source URLs (verified 2026-08-16)

- Visual regression tools 2026 — https://saucelabs.com/resources/blog/comparing-the-20-best-visual-testing-tools-of-2026
- Percy vs Applitools vs Chromatic — https://crosscheck.cloud/blogs/percy-vs-applitools-vs-chromatic-visual-regression-testing/
- Playwright visual comparisons — https://playwright.dev/docs/test-snapshots
- Best visual regression tools — https://bug0.com/knowledge-base/visual-regression-testing-tools
