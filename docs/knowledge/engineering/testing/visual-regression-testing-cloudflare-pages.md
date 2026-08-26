# visual-regression-testing-cloudflare-pages

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

A CSS change ships to production looking fine on the
developer's 27-inch monitor but breaks the mobile layout
on an iPhone 15. The team has no automated baseline for
what the page is supposed to look like on a 390 px viewport
against a real Cloudflare Pages CDN build — only unit tests
and a manual QA checklist that is skipped under deadline
pressure.

## Context

Visual regression testing captures screenshots of a running
page and diffs them against committed baseline images.
For Cloudflare Pages this means: (1) deploying to a preview
URL, (2) running Playwright against that URL with mobile
and desktop viewport configurations, (3) comparing
screenshots to baselines checked into the repository, and
(4) failing the CI pipeline when the pixel diff exceeds a
configured threshold. Playwright's built-in
`toHaveScreenshot()` matcher handles capture, diff, and
threshold in one call, with no external service required.
Percy or Chromatic are alternatives when a central approval
UI is needed.

## Project Setup

Install dependencies:

```bash
npm install --save-dev \
  @playwright/test \
  playwright-expect-screenshot   # optional: extra matchers
npx playwright install chromium webkit
```

`playwright.config.ts` for visual regression:

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir:         './tests/visual',
  snapshotDir:     './tests/visual/__snapshots__',
  updateSnapshots: process.env.UPDATE_SNAPSHOTS === '1'
    ? 'all'
    : 'none',

  expect: {
    // Allow up to 0.2 % pixel difference (anti-aliasing)
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.002,
      threshold:         0.1,  // per-pixel colour delta
      animations:        'disabled',
    },
  },

  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:8788',
    // Reduce flakiness from font rendering differences
    colorScheme: 'light',
    // Disable transition animations in all tests
    contextOptions: {
      reducedMotion: 'reduce',
    },
  },

  projects: [
    {
      name: 'desktop-chrome',
      use:  { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile-chrome',
      use:  { ...devices['Pixel 7'] },
    },
    {
      name: 'mobile-safari',
      use:  {
        ...devices['iPhone 15'],
        // Force WebKit on Linux for consistent font rendering
        channel: undefined,
      },
    },
  ],
});
```

## Capturing Baselines

Baselines are committed to the repository under
`tests/visual/__snapshots__/`. The snapshot name encodes
the test name and browser project to prevent cross-device
baseline collision:

```ts
// tests/visual/homepage.spec.ts
import { test, expect } from '@playwright/test';

test('homepage hero above the fold', async ({ page }) => {
  await page.goto('/');

  // Wait for LCP image and web fonts to settle
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(300); // font swap settle

  await expect(page).toHaveScreenshot(
    'homepage-hero.png',
    { fullPage: false }           // viewport crop only
  );
});

test('homepage full page scroll', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  await expect(page).toHaveScreenshot(
    'homepage-full.png',
    { fullPage: true }
  );
});
```

Snapshot file naming Playwright generates:

```
__snapshots__/
  homepage.spec.ts-snapshots/
    homepage-hero-desktop-chrome-linux.png
    homepage-hero-mobile-chrome-linux.png
    homepage-hero-mobile-safari-linux.png
    homepage-full-desktop-chrome-linux.png
    ...
```

The `-linux` suffix is appended automatically by Playwright
to distinguish OS-specific renders. Do not rename these
files manually.

## Updating Baselines

Update baselines when a visual change is intentional:

```bash
# Regenerate all snapshots against the current preview URL
UPDATE_SNAPSHOTS=1 \
BASE_URL=https://abc123.example project.pages.dev \
  npx playwright test tests/visual/ \
    --project=desktop-chrome \
    --project=mobile-chrome \
    --project=mobile-safari

# Commit the updated baselines
git add tests/visual/__snapshots__/
git commit -m "chore: update visual baselines for nav redesign"
```

Never update baselines in the same PR that introduces a
functional change — reviewers cannot verify the screenshot
diff is intentional.

## Mobile vs Desktop Comparison Workflow

Run the same spec file across all three projects and
compare the diff report:

```ts
// tests/visual/nav.spec.ts
import { test, expect } from '@playwright/test';

test('navigation bar renders correctly', async ({
  page,
  isMobile,
}) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  if (isMobile) {
    // Hamburger closed state
    await expect(
      page.locator('header')
    ).toHaveScreenshot('nav-mobile-closed.png');

    // Open the hamburger and capture
    await page.getByRole('button', {
      name: /menu/i,
    }).click();
    await page.waitForSelector('[data-menu-open="true"]');
    await expect(
      page.locator('[data-menu-open="true"]')
    ).toHaveScreenshot('nav-mobile-open.png');
  } else {
    await expect(
      page.locator('header')
    ).toHaveScreenshot('nav-desktop.png');
  }
});
```

Clip individual components to avoid noise from dynamic
content below the fold:

```ts
test('product card layout', async ({ page }) => {
  await page.goto('/products/widget');
  await page.waitForLoadState('networkidle');

  const card = page.getByTestId('product-card').first();
  await expect(card).toHaveScreenshot('product-card.png', {
    // clip to the card bounding box
    clip: await card.boundingBox() ?? undefined,
  });
});
```

## CI Pipeline Integration

```yaml
# .github/workflows/visual.yml
name: Visual regression

on:
  pull_request:
    branches: [main]

jobs:
  visual:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - run: npm ci

      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium webkit

      - name: Deploy preview to Cloudflare Pages
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler pages deploy ./dist \
            --project-name example project \
            --branch "${{ github.head_ref }}" \
            2>&1 | tee /tmp/deploy.log
          URL=$(grep -oP 'https://[^\s]+pages\.dev' \
            /tmp/deploy.log | tail -1)
          echo "PAGES_URL=$URL" >> "$GITHUB_OUTPUT"

      - name: Run visual regression tests
        env:
          BASE_URL: ${{ steps.deploy.outputs.PAGES_URL }}
        run: |
          npx playwright test tests/visual/ \
            --reporter=html \
            --reporter=github

      - name: Upload Playwright report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report-${{ github.sha }}
          path: playwright-report/
          retention-days: 14
```

The HTML report includes side-by-side diffs for any
failing snapshot. Download the artifact from the Actions
UI to review the diff locally.

## Baseline Management Strategy

| Scenario                          | Action                        |
|-----------------------------------|-------------------------------|
| Intentional visual change         | `UPDATE_SNAPSHOTS=1` + commit |
| Accidental diff (font/animation)  | Fix flakiness; rerun test     |
| New component added               | Run once to create baseline   |
| Old component removed             | Delete snapshot files in PR   |
| OS/browser version upgrade in CI  | Regenerate all baselines      |

Pin the Playwright version in `package.json` to prevent
baseline drift from upstream rendering changes:

```json
{
  "devDependencies": {
    "@playwright/test": "1.48.2"
  }
}
```

Use `npx playwright install --with-deps chromium webkit`
in CI (not just `install`) to pin the browser binary to
the version bundled with the installed `@playwright/test`.

## Anti-patterns

- Storing baselines in `.gitignore` — every CI run then
  regenerates them, turning regressions invisible.
- Using `fullPage: true` for all screenshots — scrolling
  loads lazy images and dynamic content that changes
  between runs; prefer viewport crops or explicit waits.
- Setting `maxDiffPixelRatio: 0` — anti-aliasing between
  OS font renderers causes constant failures on clean runs.
- Running mobile and desktop snapshots against the same
  snapshot file — they render differently; Playwright
  namespaces them by project automatically, but overriding
  the snapshot name manually removes that protection.
- Updating baselines inside the same commit that fixes a
  functional bug — reviewers cannot distinguish visual
  intent from functional side-effects.

## Gotchas

- WebKit on Linux renders fonts with different hinting than
  Safari on macOS/iOS. `mobile-safari` project baselines
  generated on a Linux CI runner will diff against a macOS
  developer machine. Accept this and generate baselines
  in CI, not locally.
- `page.waitForLoadState('networkidle')` waits for 2 s of
  no network activity — images still loading from Cloudflare
  CDN may not have completed. Add an explicit wait for the
  largest image or use `page.waitForSelector('img[src]')`.
- `animations: 'disabled'` in `toHaveScreenshot` pauses
  CSS animations but does not pause JavaScript-driven
  animations (`requestAnimationFrame`). Add
  `await page.evaluate(() => document.fonts.ready)` before
  capture to ensure web fonts have loaded.
- Cloudflare edge may serve different responses on the
  first and second request (cache MISS vs HIT). Screenshots
  taken before cache warm-up may include different content
  (e.g., stale CDN banners). Warm the URL before capture.
- `snapshotPathTemplate` can be set in config to customise
  snapshot paths. If set, the `-linux` OS suffix is still
  appended unless `snapshotSuffix` is explicitly set to `''`.

## Verification

```bash
# Dry-run against localhost to confirm test setup
npx playwright test tests/visual/ \
  --project=desktop-chrome \
  --update-snapshots

# Re-run against preview URL in diff mode (no update)
BASE_URL=https://abc123.example project.pages.dev \
  npx playwright test tests/visual/ \
  --reporter=list

# Open the HTML report in the browser
npx playwright show-report
```

A 15-screenshot suite across three projects completes in
under 3 minutes against a Pages preview URL.

## Related

- `testing/playwright-visual-comparison.md`
- `testing/visual-regression-testing-percy.md`
- `testing/playwright-cloudflare-pages-e2e.md`
- `testing/screenshot-testing-patterns.md`
- `testing/playwright-mobile-device-emulation.md`

## Source URLs (verified 2026-08-22)

- https://playwright.dev/docs/screenshots
- https://playwright.dev/docs/api/class-pageassertions#page-assertions-to-have-screenshot-1
- https://playwright.dev/docs/test-snapshots
- https://developers.cloudflare.com/pages/how-to/preview-deployments/
- https://playwright.dev/docs/test-projects
