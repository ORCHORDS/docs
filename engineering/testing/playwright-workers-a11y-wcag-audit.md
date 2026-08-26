# Playwright Workers WCAG Accessibility Audit

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers app serves HTML pages (via Workers Sites, Pages Functions, or a
Hono SSR Worker). You want automated WCAG 2.1 AA / 2.2 AA accessibility checks that
run in CI on every PR, covering real rendered output rather than static HTML. Manual
audits with screen readers are slow; Lighthouse CI gives one aggregate score; you need
per-violation, per-element reporting that can gate the PR and link directly to the
failing node.

## Context

`axe-core` is the industry-standard WCAG engine. Playwright injects axe into the live
page, runs the audit, and returns structured violations. The `@axe-core/playwright`
adapter provides a first-class integration. Together with a Workers-backed local server
(Wrangler dev or `playwright-webserver`), you get full-stack accessibility CI.

Key WCAG rule sets used in production audits:
- `wcag2a`, `wcag2aa` — WCAG 2.1 A/AA
- `wcag21aa` — WCAG 2.1 AA (alias)
- `wcag22aa` — WCAG 2.2 AA
- `best-practice` — non-normative but widely enforced

---

## Project Setup

```bash
npm install --save-dev @axe-core/playwright axe-core playwright
```

```typescript
// playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/a11y",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:8787",
    headless: true,
  },
  webServer: {
    command: "npx wrangler dev --port 8787 --local",
    url: "http://localhost:8787",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
```

---

## Axe Fixture

```typescript
// tests/a11y/fixtures.ts
import { test as base, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

export type A11yFixtures = {
  makeAxeBuilder: () => AxeBuilder;
};

export const test = base.extend<A11yFixtures>({
  makeAxeBuilder: async ({ page }, use) => {
    const buildAxe = () =>
      new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .exclude("#cookie-banner") // Exclude third-party widgets outside your control.
        .disableRules(["color-contrast"]); // Opt out individually only with documented rationale.
    await use(buildAxe);
  },
});

export { expect };
```

---

## Page-Level Audit Tests

```typescript
// tests/a11y/homepage.spec.ts
import { test, expect } from "./fixtures";

test.describe("Homepage WCAG audit", () => {
  test("has no WCAG 2.1 AA violations", async ({ page, makeAxeBuilder }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const results = await makeAxeBuilder().analyze();

    // Attach full report for Playwright trace/report.
    await test.info().attach("axe-violations", {
      body: JSON.stringify(results.violations, null, 2),
      contentType: "application/json",
    });

    expect(results.violations).toHaveLength(0);
  });

  test("navigation landmark is present", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("nav[aria-label]")).toBeVisible();
  });

  test("all images have non-empty alt text", async ({ page }) => {
    await page.goto("/");
    const images = page.locator("img");
    const count = await images.count();
    for (let i = 0; i < count; i++) {
      const alt = await images.nth(i).getAttribute("alt");
      expect(alt, `Image ${i} missing alt`).not.toBeNull();
      expect(alt?.trim(), `Image ${i} has empty alt`).not.toBe("");
    }
  });
});
```

---

## Form Accessibility Tests

```typescript
// tests/a11y/forms.spec.ts
import { test, expect } from "./fixtures";

test.describe("Form WCAG audit", () => {
  test("login form has no violations", async ({ page, makeAxeBuilder }) => {
    await page.goto("/login");
    await page.waitForSelector("form");

    const results = await makeAxeBuilder()
      .include("form") // Scope audit to the form element only.
      .analyze();

    expect(results.violations).toHaveLength(0);
  });

  test("form error messages are announced by axe", async ({ page, makeAxeBuilder }) => {
    await page.goto("/login");
    // Trigger validation errors.
    await page.click('button[type="submit"]');
    await page.waitForSelector("[aria-live]");

    const results = await makeAxeBuilder().analyze();
    expect(results.violations).toHaveLength(0);
  });

  test("each form control has a visible label", async ({ page }) => {
    await page.goto("/login");
    const inputs = page.locator("input:not([type='hidden'])");
    const count = await inputs.count();
    for (let i = 0; i < count; i++) {
      const input = inputs.nth(i);
      const id = await input.getAttribute("id");
      const ariaLabel = await input.getAttribute("aria-label");
      const ariaLabelledby = await input.getAttribute("aria-labelledby");
      const hasLabel = id
        ? (await page.locator(`label[for="${id}"]`).count()) > 0
        : false;
      expect(
        hasLabel || ariaLabel || ariaLabelledby,
        `Input at index ${i} has no accessible label`
      ).toBeTruthy();
    }
  });
});
```

---

## Dynamic Content Audit (after JS hydration)

```typescript
// tests/a11y/dynamic.spec.ts
import { test, expect } from "./fixtures";

test("modal dialog is accessible after open", async ({ page, makeAxeBuilder }) => {
  await page.goto("/dashboard");
  await page.click('[data-testid="open-modal"]');
  await page.waitForSelector('[role="dialog"]', { state: "visible" });

  const results = await makeAxeBuilder()
    .include('[role="dialog"]')
    .analyze();

  expect(results.violations).toHaveLength(0);
});

test("expanded dropdown menu has no violations", async ({ page, makeAxeBuilder }) => {
  await page.goto("/");
  await page.click('[aria-haspopup="menu"]');
  await page.waitForSelector('[role="menu"]', { state: "visible" });

  const results = await makeAxeBuilder()
    .include('[role="menu"]')
    .analyze();

  expect(results.violations).toHaveLength(0);
});
```

---

## Generating a Violation Report as an Artifact

```typescript
// tests/a11y/report-helper.ts
import type { Result } from "axe-core";
import { TestInfo } from "@playwright/test";

export async function attachViolationReport(
  violations: Result[],
  testInfo: TestInfo
): Promise<void> {
  if (violations.length === 0) return;

  const lines = violations.flatMap((v) => [
    `## ${v.id} — ${v.impact?.toUpperCase()} — ${v.description}`,
    `Help: ${v.helpUrl}`,
    ...v.nodes.map((n) => `  - ${n.html} (${n.target.join(", ")})`),
    "",
  ]);

  await testInfo.attach("wcag-violations-report", {
    body: lines.join("\n"),
    contentType: "text/plain",
  });
}
```

---

## Anti-patterns

- Running axe on a page before JavaScript has hydrated. Dynamic components (dropdowns,
  modals, tab panels) will not be in the DOM, producing false-negative audits.
- Disabling rules globally with `.disableRules([...])` without a documented rationale
  per rule. Each disabled rule is a deliberate acceptance of a WCAG gap.
- Using `wcag2a` only. WCAG 2.1 AA is the standard required by most accessibility laws
  (ADA, EN 301 549, AODA). Always include `wcag2aa` and `wcag21aa`.
- Scoping axe to `body` and expecting it to catch violations inside `<iframe>` elements.
  axe does not cross frame boundaries without explicit configuration.
- Checking only for zero violations without asserting specific rules. A single
  `disableRules` call can make all violations disappear — assert the rule list too.

## Gotchas

- `results.incomplete` contains elements axe could not fully audit. These are not
  failures, but they are worth logging. A high incomplete count signals complex DOM that
  needs manual review.
- `color-contrast` violations are the most common false positives with SVG icons or
  transparent overlays. Audit visually before disabling the rule.
- Workers dev server (`wrangler dev`) may serve stale assets from a `.wrangler` cache.
  Use `--no-bundle` or `--force` in CI to ensure a fresh build.
- Playwright's `networkidle` wait can time out on Workers that stream SSE or long-poll.
  Use `waitForSelector` targeting a page landmark instead.
- The `axe-core` version bundled in `@axe-core/playwright` determines the WCAG version
  it can audit. Pin both packages together and update them simultaneously.

## Verification

```bash
# Run all a11y tests
npx playwright test tests/a11y/

# Run with HTML report
npx playwright test tests/a11y/ --reporter=html
npx playwright show-report
```

The HTML report shows attached JSON violation reports inline with each failing test.

## Related

- `accessibility-testing-playwright-axe-pages.md` — axe on Cloudflare Pages (static)
- `a11y-automated-testing-axe.md` — axe-core fundamentals and rule reference
- `playwright-workers-dark-mode-accessibility-testing.md` — contrast and color-scheme testing
- `lighthouse-ci-integration.md` — Lighthouse CI for overall accessibility scores

## Sources

- https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright
- https://www.deque.com/axe/core-documentation/api-documentation/
- https://www.w3.org/WAI/WCAG21/quickref/?versions=2.1
- https://playwright.dev/docs/accessibility-testing
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
