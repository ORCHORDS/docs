# Playwright Component Testing Against Cloudflare Pages Preview Deployments

- Date: 2026-08-22
- Author: example.com
- Status: production

## Catching Visual Regressions Before Merge with Per-PR Preview URLs

Cloudflare Pages automatically builds and deploys a unique preview URL for every pull request branch, giving each PR its own isolated environment. By integrating Playwright component tests into the GitHub Actions CI pipeline—pointed at the live Pages preview rather than a locally-served process—you validate the real deployed bundle, service-worker registration, and edge-cached asset behaviour, not just the local dev server.

Component-level testing with Playwright differs from full E2E: instead of navigating user journeys, each test mounts an individual component in a minimal HTML harness and asserts its rendered output. Visual regression adds a screenshot comparison layer so that a CSS change that shifts a button 2 px to the right fails the test before it reaches production. The artifact upload step preserves diff images in the Actions summary, making it easy for reviewers to approve intentional changes or reject accidental ones.

The key challenge is that the Cloudflare Pages preview URL is not known until the deployment completes. A dedicated workflow job listens for the `deployment_status` event (which Pages emits after every push), extracts the URL from the event payload, and feeds it to the Playwright job as an output variable so the tests can target the correct origin.

## Context

- Framework: any component framework (React, Svelte, Vue) hosted on Cloudflare Pages
- Test runner: `@playwright/test` 1.44+
- Visual regression: `@playwright/test` built-in `toHaveScreenshot` with pixel threshold
- CI: GitHub Actions with `deployment_status` event trigger
- Artifacts: test report and diff images uploaded with `actions/upload-artifact`

## Extracting the Pages Preview URL

```yaml
# .github/workflows/component-tests.yml
name: Playwright Component Tests

on:
  deployment_status:

jobs:
  wait-for-preview:
    if: github.event.deployment_status.state == 'success' &&
        contains(github.event.deployment_status.environment_url, 'pages.dev')
    runs-on: ubuntu-latest
    outputs:
      preview_url: ${{ steps.extract.outputs.url }}
    steps:
      - name: Extract preview URL
        id: extract
        run: |
          URL="${{ github.event.deployment_status.environment_url }}"
          echo "Preview URL: $URL"
          echo "url=$URL" >> "$GITHUB_OUTPUT"
```

## Playwright Component Test Setup

```ts
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./src",
  testMatch: "**/*.component.spec.ts",
  use: {
    baseURL: process.env.PREVIEW_URL ?? "http://localhost:8788",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  snapshotDir: "./__snapshots__",
  updateSnapshots: "missing",
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit",   use: { ...devices["Desktop Safari"] } },
  ],
  reporter: [
    ["html", { outputFolder: "playwright-report" }],
    ["github"],
  ],
});
```

```ts
// src/components/Button.component.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Button component", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the component harness page served from Pages
    await page.goto("/component-harness/button");
  });

  test("renders primary variant correctly", async ({ page }) => {
    const btn = page.getByRole("button", { name: "Submit" });
    await expect(btn).toBeVisible();
    await expect(btn).toHaveCSS("background-color", "rgb(99, 102, 241)");
  });

  test("matches visual snapshot", async ({ page }) => {
    const btn = page.getByRole("button", { name: "Submit" });
    await expect(btn).toHaveScreenshot("button-primary.png", {
      maxDiffPixelRatio: 0.01, // allow up to 1 % pixel difference
    });
  });

  test("shows focus ring on keyboard navigation", async ({ page }) => {
    await page.keyboard.press("Tab");
    const btn = page.getByRole("button", { name: "Submit" });
    await expect(btn).toBeFocused();
    await expect(btn).toHaveScreenshot("button-focused.png");
  });
});
```

## Full Actions Workflow with Artifact Reporting

```yaml
  run-tests:
    needs: wait-for-preview
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Install Playwright browsers
        run: pnpm exec playwright install --with-deps chromium webkit

      - name: Run component tests against preview
        env:
          PREVIEW_URL: ${{ needs.wait-for-preview.outputs.preview_url }}
        run: pnpm exec playwright test --project=chromium --project=webkit

      - name: Upload test report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report-${{ github.run_id }}
          path: playwright-report/
          retention-days: 14

      - name: Upload snapshot diffs
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: snapshot-diffs-${{ github.run_id }}
          path: test-results/**/*-diff.png
          retention-days: 7

      - name: Comment PR with report link
        if: always() && github.event_name == 'deployment_status'
        uses: actions/github-script@v7
        with:
          script: |
            const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
            const status = '${{ job.status }}' === 'success' ? '✅' : '❌';
            await github.rest.repos.createCommitComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              commit_sha: context.sha,
              body: `${status} Playwright component tests — view report`,
            });
```

## Anti-patterns

- Running component tests against `localhost` or the Wrangler dev server instead of the Pages preview — misses real asset hashing, CDN headers, and service-worker paths
- Checking snapshot images into the repository at full resolution — use `.gitattributes` to mark them as binary and consider storing them in a separate snapshots branch or artifact store
- Setting `maxDiffPixelRatio` to zero — sub-pixel anti-aliasing differences across browsers will cause constant false failures
- Triggering tests on `push` rather than `deployment_status` — the preview URL does not yet exist when the push event fires
- Using `--update-snapshots` in CI without a human approval gate — this silently overwrites the baseline on every run

## Gotchas

- `deployment_status` events fire for every environment (production and preview); the `contains(…, 'pages.dev')` guard filters to preview URLs only
- Pages preview URLs include the branch name slugified; special characters in branch names may cause URL-encoding issues — use `encodeURIComponent` if constructing the URL programmatically
- Cloudflare Pages build time is not included in the Actions job timer — the total time-to-green includes Pages build + Actions job
- The `github` reporter built into Playwright annotates failing tests as workflow annotations in the Actions UI, but only when `GITHUB_ACTIONS=true` is set (it is set automatically on hosted runners)
- Snapshot files differ between OS and browser engine versions; pin the exact Playwright version with `playwright install --with-deps` to keep baselines stable

## Verification

```ts
// Smoke-test the harness page is reachable before running full suite
import { test, expect } from "@playwright/test";

test("component harness is reachable at preview URL", async ({ page }) => {
  const res = await page.goto("/component-harness/button");
  expect(res?.status()).toBe(200);
  await expect(page.locator("body")).not.toBeEmpty();
});
```

## Related

- `documentation/categories/github/github-actions-e2e-playwright.md`
- `documentation/categories/github/github-actions-deploy-pages.md`
- `documentation/categories/github/github-actions-artifact-upload.md`

## Sources

- https://playwright.dev/docs/component-testing
- https://developers.cloudflare.com/pages/configuration/preview-deployments/
- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#deployment_status
