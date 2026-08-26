# vitest-browser-mode

**Issue:** Running Vitest tests in a real browser instead of jsdom
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
jsdom does not support all browser APIs (ResizeObserver, Web Animations, WebGL). Vitest browser mode runs tests in Chromium via Playwright.

## Pattern / Solution
```bash
npm install -D @vitest/browser playwright
npx playwright install chromium
```

`vitest.config.ts`:
```ts
test: {
  browser: {
    enabled: true,
    name: "chromium",
    provider: "playwright",
    headless: true,
  },
}
```

Tests run identically — no API changes:
```ts
import { render } from "@testing-library/react";
import { expect, it } from "vitest";

it("renders canvas element", () => {
  const { getByRole } = render(<CanvasChart />);
  expect(getByRole("img")).toBeInTheDocument();
});
```

## Gotchas
- Browser mode is slower than jsdom for large suites
- Not all Node.js APIs are available in browser context
- Use `@vitest/ui` for interactive debugging in browser

## Related
- `vitest-setup.md`
- `playwright-setup.md`
- `cross-browser-testing.md`
