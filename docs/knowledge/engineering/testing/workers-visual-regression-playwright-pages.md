# Visual Regression Testing with Playwright on Cloudflare Pages Preview URLs

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A CSS refactor unintentionally shifts the hero section 8 px to the left on mobile. Unit tests pass. The bug ships to production. Visual regression testing catches pixel-level changes in Pages preview deployments before merge, blocking the PR automatically.

## Context

Each `git push` to a Cloudflare Pages project creates a unique preview URL (e.g., `https://<hash>.your-project.pages.dev`). Playwright's `toHaveScreenshot` command compares a fresh screenshot against a stored baseline PNG, failing when the diff exceeds a configurable threshold. CI uploads both baseline and diff images as artifacts for human review.

---

## Section 1 — Project setup

```bash
npm install --save-dev @playwright/test
npx playwright install --with-deps chromium
```

```ts
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

const PREVIEW_URL = process.env.PAGES_PREVIEW_URL ?? 'http://localhost:8788';

export default defineConfig({
  testDir: 'tests/visual',
  // Each visual test gets 60 s — pages preview cold starts can be slow
  timeout: 60_000,
  // Fail fast on CI: no retries for visual tests
  retries: process.env.CI ? 0 : 1,
  workers: process.env.CI ? 2 : undefined,
  use: {
    baseURL: PREVIEW_URL,
    // Deterministic rendering: disable animations and fonts loading
    launchOptions: {
      args: ['--font-render-hinting=none', '--disable-lcd-text'],
    },
  },
  projects: [
    {
      name: 'chromium-desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
      },
    },
    {
      name: 'chromium-mobile',
      use: {
        ...devices['Pixel 7'],
      },
    },
  ],
  // Store baselines in version control
  snapshotDir: 'tests/visual/__snapshots__',
  // Diff images land here for CI upload
  outputDir: 'playwright-report/visual-diffs',
});
```

## Section 2 — Writing screenshot tests with `toHaveScreenshot`

```ts
// tests/visual/home.spec.ts
import { test, expect, Page } from '@playwright/test';

async function disableAnimations(page: Page): Promise<void> {
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        transition-duration: 0s !important;
      }
    `,
  });
}

async function waitForFonts(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
}

test.describe('Home page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await disableAnimations(page);
    await waitForFonts(page);
    // Wait for any above-the-fold lazy images
    await page.waitForLoadState('networkidle');
  });

  test('full page matches baseline', async ({ page }) => {
    await expect(page).toHaveScreenshot('home-full.png', {
      fullPage: true,
      // Allow up to 0.2% of pixels to differ (anti-aliasing noise)
      maxDiffPixelRatio: 0.002,
      animations: 'disabled',
    });
  });

  test('hero section matches baseline', async ({ page }) => {
    const hero = page.locator('[data-testid="hero"]');
    await expect(hero).toHaveScreenshot('home-hero.png', {
      maxDiffPixelRatio: 0.001,
    });
  });

  test('navigation bar matches baseline', async ({ page }) => {
    const nav = page.locator('nav');
    await expect(nav).toHaveScreenshot('home-nav.png', {
      maxDiffPixelRatio: 0.001,
    });
  });
});

test.describe('Pricing page', () => {
  test('pricing table matches baseline', async ({ page }) => {
    await page.goto('/pricing');
    await disableAnimations(page);
    await waitForFonts(page);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="pricing-table"]')).toHaveScreenshot(
      'pricing-table.png',
      { maxDiffPixelRatio: 0.002 }
    );
  });
});
```

## Section 3 — CI pipeline with Pages preview URL and artifact upload

```yaml
# .github/workflows/visual-regression.yml
name: Visual Regression

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  visual-regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # Fetch baseline snapshots committed to main
          fetch-depth: 0

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci
      - run: npx playwright install --with-deps chromium

      - name: Wait for Pages preview deployment
        id: pages-preview
        uses: cloudflare/pages-action@v1
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          accountId: ${{ secrets.CF_ACCOUNT_ID }}
          projectName: your-project-name
          # The action outputs `url` once the preview is live
          gitHubToken: ${{ secrets.GITHUB_TOKEN }}
          wranglerVersion: '3'

      - name: Run visual regression tests
        env:
          PAGES_PREVIEW_URL: ${{ steps.pages-preview.outputs.url }}
        run: npx playwright test --project=chromium-desktop --project=chromium-mobile

      - name: Upload diff report on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: visual-regression-diffs-${{ github.run_id }}
          path: |
            playwright-report/
            tests/visual/__snapshots__/
          retention-days: 14

      - name: Comment PR with diff link on failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## Visual Regression Failed

            Screenshot diffs are available in the CI artifacts.

            To update baselines locally:
            \`\`\`bash
            PAGES_PREVIEW_URL=${{ steps.pages-preview.outputs.url }} npx playwright test --update-snapshots
            git add tests/visual/__snapshots__/
            git commit -m "chore(visual): update screenshot baselines"
            \`\`\`
            `
            });
```

## Section 4 — Baseline update workflow

```ts
// scripts/update-baselines.ts
/**
 * Run this script when intentional UI changes require updating all baselines.
 * It runs Playwright with --update-snapshots against the Pages preview URL,
 * then stages the new PNG files for commit.
 */
import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';

const previewUrl = process.env.PAGES_PREVIEW_URL;
if (!previewUrl) {
  console.error('PAGES_PREVIEW_URL environment variable is required.');
  process.exit(1);
}

console.log(`Updating baselines against: ${previewUrl}`);

try {
  execSync(
    `npx playwright test --update-snapshots --project=chromium-desktop --project=chromium-mobile`,
    {
      env: { ...process.env, PAGES_PREVIEW_URL: previewUrl },
      stdio: 'inherit',
    }
  );
} catch {
  // --update-snapshots exits 0 even when new screenshots are written.
  // It only exits non-zero on infrastructure errors.
  console.error('Playwright failed during baseline update.');
  process.exit(1);
}

// Stage only PNG baseline files
execSync('git add tests/visual/__snapshots__/', { stdio: 'inherit' });

const status = execSync('git status --short tests/visual/__snapshots__/').toString();
if (!status.trim()) {
  console.log('No baseline changes detected.');
} else {
  console.log('Staged baseline changes:');
  console.log(status);
  console.log('\nCommit with:');
  console.log('  git commit -m "chore(visual): update screenshot baselines"');
}
```

```bash
# Usage
PAGES_PREVIEW_URL=https://abc123.your-project.pages.dev \
  npx ts-node --esm scripts/update-baselines.ts
```

## Anti-patterns

- **Committing baseline PNGs from local machines** — rendering differs across OS and GPU. Always generate baselines in the same CI environment (Linux + chromium headless) that runs the comparison.
- **Setting `maxDiffPixelRatio: 0`** — font anti-aliasing and sub-pixel rendering produce 1-3 pixel differences that are not regressions. Use `0.001`–`0.005` for element screenshots.
- **Not waiting for `networkidle`** — lazy-loaded images or web fonts that haven't loaded produce noisy diff noise on every run.
- **Running visual tests on every commit** — they are slow and flaky under heavy load. Trigger only on PRs via path filter or a label gate.

## Gotchas

- Pages preview URLs are unique per push. The `PAGES_PREVIEW_URL` must be read from the deployment action's output, not hardcoded.
- `cloudflare/pages-action` does not block until the build is deployed — poll the URL with a `wait-on` step or use the action's built-in `wranglerVersion` + `command` to confirm liveness.
- Playwright snapshots include the project name in the filename (e.g., `home-full-chromium-desktop.png`). Account for this in `.gitignore` and artifact paths.
- Dynamic content (timestamps, randomised ads) must be masked via `page.addStyleTag({ content: '[data-dynamic] { visibility: hidden; }' })` before screenshotting.

## Verification

```bash
# Run visual tests against local wrangler pages dev
npx wrangler pages dev ./dist --port 8788 &
npx playwright test --project=chromium-desktop

# Update baselines
PAGES_PREVIEW_URL=http://localhost:8788 npx playwright test --update-snapshots

# View the HTML report
npx playwright show-report
```

## Related

- `documentation/docs/policies/testing/workers-api-versioning-backward-compat-test.md`
- `documentation/ci/workers-github-actions-matrix.md`
- `documentation/pages/workers-pages-preview-deployment.md`

## Sources

- https://playwright.dev/docs/screenshots
- https://playwright.dev/docs/test-snapshots
- https://developers.cloudflare.com/pages/how-to/preview-deployments/
- https://github.com/cloudflare/pages-action
