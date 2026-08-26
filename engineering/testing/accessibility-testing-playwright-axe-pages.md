# Accessibility Testing with Playwright and axe-core on Cloudflare Pages

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project Pages deploys ship UI regressions that only surface in manual screen-reader audits: missing ARIA labels on icon buttons, insufficient colour contrast after a brand token change, and focus traps that break keyboard navigation on mobile viewports. Manual audits catch issues late and inconsistently across contributors.

## Context

axe-core is the de-facto open-source accessibility rule engine. `@axe-core/playwright` integrates it with Playwright so each test page is scanned against WCAG 2.1 AA rules in the same browser context used for E2E tests. example project runs these scans against Cloudflare Pages preview deployments created per pull request, gating merge on zero violations. Mobile viewport scans run in parallel using Playwright device emulation.

Versions: `@axe-core/playwright` 4.x, `playwright` 1.x, Node 20.

## Installation

```bash
npm install --save-dev @axe-core/playwright axe-core
```

No separate axe binary is needed — `@axe-core/playwright` injects axe into the page at runtime.

## Basic Page Scan

```typescript
// tests/a11y/home.a11y.ts
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("Home page accessibility", () => {
  test("has no WCAG 2.1 AA violations", async ({ page }) => {
    await page.goto("/");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();

    expect(results.violations).toEqual([]);
  });
});
```

When `violations` is non-empty, Playwright reports the full axe violation list including impact, affected nodes, and help URLs.

## Mobile Viewport Accessibility

Create Playwright projects for mobile emulation in `playwright.config.ts`:

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  use: {
    baseURL: process.env.PAGES_URL ?? "http://localhost:8788",
  },
  projects: [
    {
      name: "desktop-chrome",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-iphone-14",
      use: { ...devices["iPhone 14"] },
    },
    {
      name: "mobile-android",
      use: { ...devices["Pixel 7"] },
    },
  ],
});
```

Mobile a11y test using the device project:

```typescript
// tests/a11y/track-player.a11y.ts
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("Track player mobile accessibility", () => {
  test("play/pause button is accessible on iPhone 14", async ({ page }) => {
    await page.goto("/tracks/1");
    await page.waitForSelector("[data-testid='player']");

    const results = await new AxeBuilder({ page })
      .include("[data-testid='player']")  // scope to player component
      .withTags(["wcag21aa"])
      .analyze();

    expect(results.violations).toEqual([]);
  });
});
```

`.include()` scopes the scan to a CSS selector, reducing noise from unrelated page regions.

## WCAG 2.1 AA Gate

axe rule tags relevant to example project:

| Tag          | Coverage                                                  |
|--------------|-----------------------------------------------------------|
| `wcag2a`     | WCAG 2.0 Level A — baseline                               |
| `wcag2aa`    | WCAG 2.0 Level AA — colour contrast, labels               |
| `wcag21aa`   | WCAG 2.1 additions — touch targets, motion, reflow        |
| `best-practice` | Non-normative recommendations — useful but not gating  |

To gate on AA only and surface best-practice as warnings:

```typescript
const aaResults = await new AxeBuilder({ page })
  .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
  .analyze();

const bpResults = await new AxeBuilder({ page })
  .withTags(["best-practice"])
  .analyze();

// Hard gate
expect(aaResults.violations).toEqual([]);

// Soft warning — annotate but do not fail
if (bpResults.violations.length > 0) {
  test.info().annotations.push({
    type: "a11y-best-practice",
    description: JSON.stringify(bpResults.violations.map(v => v.id)),
  });
}
```

## Running Against Cloudflare Pages Preview

```yaml
# .github/workflows/a11y.yml
name: Accessibility

on:
  pull_request:

jobs:
  a11y:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npx playwright install --with-deps chromium

      - name: Get Pages preview URL
        id: pages
        run: |
          # Wait for Pages deployment to be ready and capture URL
          PAGES_URL=$(gh api \
            "repos/${{ github.repository }}/deployments" \
            --jq '[.[] | select(.environment=="preview")] | first | .payload.url // empty' \
            2>/dev/null || echo "")
          echo "url=${PAGES_URL:-http://localhost:8788}" >> "$GITHUB_OUTPUT"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Run a11y tests against preview
        run: npx playwright test tests/a11y/
        env:
          PAGES_URL: ${{ steps.pages.outputs.url }}

      - name: Upload Playwright report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: a11y-report
          path: playwright-report/
```

## CI Report Format

Playwright's built-in HTML reporter includes axe violation details when `expect(results.violations).toEqual([])` fails:

```
  ✗ Home page accessibility › has no WCAG 2.1 AA violations

    AssertionError: expected [] but received:
    [
      {
        id: 'color-contrast',
        impact: 'serious',
        description: 'Elements must have sufficient color contrast',
        nodes: [
          {
            html: '<span class="track-title" style="color:#9CA3AF">...</span>',
            failureSummary: 'Fix: Element has insufficient color contrast of 2.94...',
            target: ['.track-title']
          }
        ]
      }
    ]
```

For richer CI output, configure the JSON reporter and post results as a PR comment:

```typescript
// tests/a11y/helpers/report-violations.ts
import type { AxeResults } from "axe-core";
import { test } from "@playwright/test";

export function attachViolations(results: AxeResults): void {
  for (const v of results.violations) {
    test.info().attachments.push({
      name:  `axe-${v.id}`,
      contentType: "application/json",
      body: Buffer.from(JSON.stringify(v, null, 2)),
    });
  }
}
```

## Disabling Rules for Known Exceptions

```typescript
const results = await new AxeBuilder({ page })
  .withTags(["wcag21aa"])
  .disableRules([
    "color-contrast",    // tracked in GH issue #<number> — design system update pending
  ])
  .analyze();
```

| Practice                        | Recommendation                                         |
|---------------------------------|--------------------------------------------------------|
| Disable rules                   | Document with a linked issue; review monthly           |
| `.exclude()` selectors           | Use for third-party embeds only (e.g. Turnstile widget)|
| `incomplete` results             | Review separately — axe could not determine pass/fail  |

## Anti-patterns

- Calling `.analyze()` before interactive content has loaded — axe scans the DOM as it exists at call time; wait for stable state first.
- Scanning the entire page when only testing a new component — use `.include()` to reduce false positives from unrelated issues.
- Disabling `color-contrast` globally to silence CI — create a tracked exception per rule and per component.
- Running a11y tests only on desktop viewports — mobile has distinct touch target and reflow requirements under WCAG 2.1.
- Ignoring `incomplete` results — they indicate ambiguous cases that a human must review.

## Gotchas

- `@axe-core/playwright` 4.x requires `axe-core` as a peer dependency; mismatched versions cause rule definition errors at runtime.
- Cloudflare Pages preview URLs are only available after the deployment completes — add a step to poll the deployment API or use `wrangler pages deployment list` to retrieve it.
- axe runs inside the browser page; a CSP that blocks inline scripts will prevent axe injection — add `'unsafe-eval'` to `script-src` in the test environment only (not production).
- Playwright `devices["iPhone 14"]` sets `isMobile: true` and a narrow viewport; some axe rules (touch-target) only fire on mobile viewports.
- The `wcag21aa` tag does not include `wcag2a` and `wcag2aa` — always pass all three tags together for full AA coverage.

## Verification

```bash
# Run all a11y tests locally against dev server
PAGES_URL=http://localhost:8788 npx playwright test tests/a11y/ --reporter=list

# Run only mobile projects
npx playwright test tests/a11y/ --project=mobile-iphone-14

# Show HTML report in browser
npx playwright show-report

# Print raw axe violations for a page (quick check)
npx playwright test tests/a11y/home.a11y.ts --reporter=line
```

Expected green output:

```
Running 3 tests using 3 workers
  ✓ [desktop-chrome] Home page accessibility › has no WCAG 2.1 AA violations (1.2s)
  ✓ [mobile-iphone-14] Home page accessibility › has no WCAG 2.1 AA violations (1.4s)
  ✓ [mobile-android] Home page accessibility › has no WCAG 2.1 AA violations (1.3s)

3 passed (4.5s)
```

## Related

- `a11y-automated-testing-axe.md`
- `playwright-cloudflare-pages-e2e.md`
- `playwright-mobile-device-emulation.md`
- `testing-library-accessibility-queries.md`
- `lighthouse-ci-integration.md`
- `visual-regression-testing-cloudflare-pages.md`

## Sources

- https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright
- https://www.deque.com/axe/core-documentation/api-documentation/
- https://playwright.dev/docs/accessibility-testing
- https://developers.cloudflare.com/pages/configuration/preview-deployments/
- https://www.w3.org/WAI/WCAG21/quickref/
