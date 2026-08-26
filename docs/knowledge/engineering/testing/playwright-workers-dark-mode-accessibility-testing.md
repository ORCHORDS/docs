# Playwright Workers Dark Mode Accessibility Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A UI served from a Cloudflare Worker (or Pages Function) supports a `prefers-color-scheme`
media query for dark mode. Stakeholders report that in dark mode:

- Text contrast ratios fall below WCAG 2.1 AA (4.5:1 for normal text, 3:1 for
  large text).
- Focus rings become invisible against dark backgrounds.
- SVG icons lose colour and become unrecognisable.
- The `aria-label` on the colour-mode toggle button is missing or wrong.

You need Playwright tests that emulate dark mode at the browser level and run axe-core
accessibility audits against the Worker-served UI in both colour schemes.

---

## Context

Playwright provides `colorScheme` in browser context options and as a `page.emulateMedia`
call. Combined with `@axe-core/playwright`, the suite can:

1. Load the page in `light` and `dark` schemes.
2. Run an axe audit in each scheme.
3. Assert specific WCAG rules (colour contrast, focus-visible).
4. Take annotated screenshots as regression anchors.
5. Run against a locally spawned Wrangler dev server so tests are deterministic.

---

## Project Layout

```
e2e/
  axe.setup.ts          # shared axe config
  dark-mode.spec.ts     # main spec
  fixtures.ts           # Page Object and custom fixtures
playwright.config.ts
wrangler.toml
```

---

## Dependencies

```bash
npm install --save-dev \
  @playwright/test \
  @axe-core/playwright \
  axe-core
```

---

## Playwright Config

```ts
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  webServer: {
    command: 'wrangler dev --local --port 8787',
    url: 'http://localhost:8787',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  use: {
    baseURL: 'http://localhost:8787',
  },
  projects: [
    {
      name: 'chromium-light',
      use: { ...devices['Desktop Chrome'], colorScheme: 'light' },
    },
    {
      name: 'chromium-dark',
      use: { ...devices['Desktop Chrome'], colorScheme: 'dark' },
    },
    {
      name: 'mobile-dark',
      use: { ...devices['iPhone 14'], colorScheme: 'dark' },
    },
  ],
});
```

---

## Shared Axe Configuration

```ts
// e2e/axe.setup.ts
import type { AxeBuilder } from '@axe-core/playwright';

export const AXE_WCAG_RULES = ['wcag2a', 'wcag2aa', 'wcag21aa'];

// Rules specifically relevant to dark-mode regressions
export const DARK_MODE_CRITICAL_RULES = [
  'color-contrast',
  'color-contrast-enhanced',
  'focus-visible',
  'image-alt',
  'label',
  'link-name',
  'button-name',
];

export function configureDarkAxe(builder: AxeBuilder): AxeBuilder {
  return builder
    .withTags(AXE_WCAG_RULES)
    .withRules(DARK_MODE_CRITICAL_RULES)
    .exclude('#cookie-banner'); // known 3rd-party widget
}
```

---

## Custom Fixtures

```ts
// e2e/fixtures.ts
import { test as base, expect } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';

type DarkModeFixtures = {
  axeBuilder: AxeBuilder;
};

export const test = base.extend<DarkModeFixtures>({
  axeBuilder: async ({ page }, use) => {
    const builder = new AxeBuilder({ page });
    await use(builder);
  },
});

export { expect };
```

---

## Main Spec

```ts
// e2e/dark-mode.spec.ts
import { test, expect } from './fixtures';
import { configureDarkAxe } from './axe.setup';
import { AxeBuilder } from '@axe-core/playwright';

const PAGES_TO_AUDIT = ['/', '/products', '/about', '/checkout'];

for (const path of PAGES_TO_AUDIT) {
  test.describe(`${path} — accessibility`, () => {
    test.beforeEach(async ({ page }) => {
      await page.goto(path);
      // Wait for fonts and images to settle before contrast checks
      await page.waitForLoadState('networkidle');
    });

    test('passes axe audit in current colour scheme', async ({ page, axeBuilder }) => {
      const results = await configureDarkAxe(axeBuilder).analyze();

      expect(results.violations, formatViolations(results.violations)).toHaveLength(0);
    });

    test('colour-mode toggle has accessible label', async ({ page }) => {
      const toggle = page.getByRole('button', { name: /toggle (dark|light) mode/i });
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute('aria-label');
    });

    test('all images have meaningful alt text', async ({ page }) => {
      const images = page.locator('img:not([role="presentation"])');
      const count  = await images.count();
      for (let i = 0; i < count; i++) {
        const alt = await images.nth(i).getAttribute('alt');
        expect(alt, `img[${i}] missing alt text`).toBeTruthy();
        expect(alt!.trim(), `img[${i}] alt is empty string`).not.toBe('');
      }
    });

    test('focus ring is visible on interactive elements', async ({ page }) => {
      // Tab through focusable elements and assert outline is not 'none'
      const focusable = page.locator('a[href], button:not([disabled]), input, select, textarea, [tabindex="0"]');
      const count     = await focusable.count();
      const sample    = Math.min(count, 5); // spot-check up to 5

      for (let i = 0; i < sample; i++) {
        await focusable.nth(i).focus();
        const outline = await focusable.nth(i).evaluate(
          (el) => getComputedStyle(el).outlineStyle
        );
        expect(outline, `Element ${i} has no visible focus outline`).not.toBe('none');
      }
    });
  });
}

// ── Dark-mode specific visual regression ─────────────────────────────────────
test.describe('dark mode visual regression', () => {
  test.use({ colorScheme: 'dark' });

  test('homepage renders correctly in dark mode', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveScreenshot('homepage-dark.png', {
      fullPage: true,
      maxDiffPixelRatio: 0.02,
    });
  });

  test('nav background is not white in dark mode', async ({ page }) => {
    await page.goto('/');
    const nav = page.locator('nav');
    await expect(nav).toBeVisible();

    const bgColor = await nav.evaluate(
      (el) => getComputedStyle(el).backgroundColor
    );
    // Assert it is not pure white (rgb(255, 255, 255))
    expect(bgColor).not.toBe('rgb(255, 255, 255)');
  });

  test('primary text meets contrast ratio in dark mode', async ({ page }) => {
    await page.goto('/');
    // axe-core colour-contrast rule covers this; this test demonstrates
    // targeted single-rule execution for CI speed
    const results = await new AxeBuilder({ page })
      .withRules(['color-contrast'])
      .analyze();

    expect(results.violations, formatViolations(results.violations)).toHaveLength(0);
  });
});

// ── Scheme switching ──────────────────────────────────────────────────────────
test.describe('colour scheme toggling', () => {
  test('toggle button switches between dark and light', async ({ page }) => {
    await page.goto('/');
    const html   = page.locator('html');
    const toggle = page.getByRole('button', { name: /toggle (dark|light) mode/i });

    const initialScheme = await html.getAttribute('data-theme');
    await toggle.click();
    const afterScheme   = await html.getAttribute('data-theme');

    expect(afterScheme).not.toBe(initialScheme);
  });

  test('preference is persisted in localStorage', async ({ page }) => {
    await page.goto('/');
    const toggle = page.getByRole('button', { name: /toggle (dark|light) mode/i });
    await toggle.click();

    const stored = await page.evaluate(() => localStorage.getItem('color-scheme'));
    expect(stored).toMatch(/^(dark|light)$/);
  });

  test('persisted preference is applied on reload', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.setItem('color-scheme', 'dark'));
    await page.reload();

    const theme = await page.locator('html').getAttribute('data-theme');
    expect(theme).toBe('dark');
  });
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatViolations(violations: Awaited<ReturnType<AxeBuilder['analyze']>>['violations']) {
  return violations
    .map((v) => `[${v.id}] ${v.help}: ${v.nodes.map((n) => n.target.join(', ')).join(' | ')}`)
    .join('\n');
}
```

---

## Running Against a Deployed Worker (Staging)

```ts
// playwright.config.staging.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: process.env.STAGING_URL },
  projects: [
    { name: 'dark-chromium', use: { ...devices['Desktop Chrome'], colorScheme: 'dark' } },
    { name: 'light-chromium', use: { ...devices['Desktop Chrome'], colorScheme: 'light' } },
  ],
});
```

```bash
STAGING_URL=https://staging.example.com \
  npx playwright test --config playwright.config.staging.ts
```

---

## CI (GitHub Actions)

```yaml
# .github/workflows/dark-mode-a11y.yml
name: Dark Mode A11y
on: [push, pull_request]

jobs:
  dark-mode-a11y:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - run: npm ci
      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium
      - name: Install wrangler
        run: npm install -g wrangler
      - name: Run dark mode tests
        run: npx playwright test --project=chromium-dark --project=chromium-light
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
```

---

## Anti-patterns

- **Asserting exact hex colour values** — computed colours vary by OS and font
  rendering. Use axe contrast rules instead of string-matching computed styles.
- **Skipping `waitForLoadState('networkidle')`** — fonts load asynchronously;
  contrast checks against un-rendered text produce false negatives.
- **One test for all pages** — group pages with `for` + `test.describe` so
  failures are traceable to a specific route.
- **Ignoring mobile projects** — dark mode rendering can differ significantly on
  mobile viewport due to touch-target sizing and different CSS breakpoints.
- **Using `page.screenshot` instead of `expect(page).toHaveScreenshot`** —
  only the Playwright assertion method integrates with the snapshot update workflow
  (`--update-snapshots`).

---

## Gotchas

- `colorScheme: 'dark'` in Playwright project config sets the browser-level media
  feature, not a JavaScript flag. Workers that serve different HTML based on a
  cookie/header won't receive it; test the CSS `@media` path, not a server-side
  branch, unless you also set the appropriate request header.
- axe-core `color-contrast` rule requires the element to be visible and painted.
  Lazy-loaded content not yet in the viewport may be skipped — scroll to it or
  use `waitForSelector`.
- Screenshot diffs have a per-pixel threshold (`maxDiffPixelRatio`). Anti-aliasing
  differences between CI runners and local machines cause false failures; set
  `threshold: 0.2` per pixel when needed.
- The `color-contrast-enhanced` rule enforces AAA (7:1 ratio) — often too strict
  for production. Disable it unless your spec explicitly targets AAA.

---

## Verification

```bash
# run only dark-mode project
npx playwright test --project=chromium-dark --reporter=html

# update golden screenshots after intentional design change
npx playwright test --project=chromium-dark --update-snapshots

# run axe in headed mode to see violations highlighted
npx playwright test --headed --project=chromium-dark
```

All `violations` arrays should be empty. The toggle tests should pass across all
colour-scheme configurations.

---

## Related

- `accessibility-testing-playwright-axe-pages.md`
- `a11y-automated-testing-axe.md`
- `playwright-visual-comparison.md`
- `playwright-workers-auth-flow-session-persistence-e2e.md`
- `playwright-cloudflare-pages-e2e.md`

---

## Sources

- Playwright `colorScheme` docs: https://playwright.dev/docs/emulation#color-scheme-and-media
- `@axe-core/playwright`: https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright
- WCAG 2.1 contrast criteria: https://www.w3.org/TR/WCAG21/#contrast-minimum
- Cloudflare Workers serving HTML: https://developers.cloudflare.com/workers/examples/return-html/
