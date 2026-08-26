# a11y-automated-testing-axe

**Issue:** Catching accessibility violations automatically in component and E2E tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Accessibility issues are found late in QA or by users with assistive technology because there are no automated checks in the development workflow.

## Pattern / Solution
Integrate `axe-core` via framework adapters:

**Component tests (Vitest + Testing Library):**
```ts
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
expect.extend(toHaveNoViolations);

test("LoginForm has no accessibility violations", async () => {
  const { container } = render(<LoginForm />);
  expect(await axe(container)).toHaveNoViolations();
});
```

**Playwright:**
```ts
import AxeBuilder from "@axe-core/playwright";

test("homepage is accessible", async ({ page }) => {
  await page.goto("/");
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```

Focus axe on the WCAG 2.1 AA rule set as a baseline. Exclude known third-party components with `.exclude(".third-party-widget")` and file tracking issues for them separately.

## Gotchas
- axe-core catches ~30–40% of accessibility issues; it does not replace manual keyboard and screen-reader testing.
- New violations introduced by a dependency upgrade show up as unexpected test failures — use `--reporter=verbose` to identify the violating element.
- Do not suppress violations with blanket exclusions; suppress only specific, documented exceptions.

## Related
- testing-library-accessibility-queries
- playwright-setup
- lighthouse-ci-integration
