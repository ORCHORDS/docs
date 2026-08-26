# Playwright Component Testing for Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You have a React or Preact component library deployed on Cloudflare Pages and want fast, isolated
component-level tests that mount individual components in a real browser without spinning up the
full Pages app.

## Context
Cloudflare Pages projects commonly use Vite as the build tool and React/Preact for the UI layer.
Playwright's experimental component-testing mode (`@playwright/experimental-ct-react`) mounts
components into an iframe served by a Vite dev server running inside the test process, giving you
real browser rendering without a full E2E server. This complements wrangler-based E2E tests by
covering component behaviour, accessibility, and visual state in milliseconds per test.

## Installing and Configuring

```bash
pnpm add -D @playwright/experimental-ct-react playwright @vitejs/plugin-react
# Install browser binaries
pnpm playwright install chromium
```

```ts
// playwright-ct.config.ts
import { defineConfig, devices } from "@playwright/experimental-ct-react";
import react from "@vitejs/plugin-react";

export default defineConfig({
  testDir: "./src",
  testMatch: "**/*.ct.tsx",
  snapshotDir: "./__snapshots__",
  timeout: 10_000,
  use: {
    ctPort: 3100,
    ctViteConfig: {
      plugins: [react()],
      resolve: {
        alias: { "@": "/src" },
      },
    },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
```

Add a `ct` script to `package.json`:

```json
{
  "scripts": {
    "test:ct": "playwright test -c playwright-ct.config.ts"
  }
}
```

## Writing Component Tests

```tsx
// src/components/StatusBadge.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import { StatusBadge } from "./StatusBadge";

test("renders online status", async ({ mount }) => {
  const component = await mount(<StatusBadge status="online" />);
  await expect(component).toContainText("Online");
  await expect(component).toHaveCSS("background-color", "rgb(34, 197, 94)");
});

test("renders offline status", async ({ mount }) => {
  const component = await mount(<StatusBadge status="offline" />);
  await expect(component).toContainText("Offline");
  await expect(component).toHaveAttribute("aria-label", "offline");
});

test("calls onDismiss when badge is clicked", async ({ mount }) => {
  let dismissed = false;
  const component = await mount(
    <StatusBadge status="error" onDismiss={() => { dismissed = true; }} />
  );
  await component.click();
  expect(dismissed).toBe(true);
});
```

## Mocking Pages Functions API Routes

Component tests run against Vite, not Pages Functions. Intercept fetch calls to API routes:

```tsx
// src/components/UserCard.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import { UserCard } from "./UserCard";

test("displays user data from API", async ({ mount, page }) => {
  // Intercept the API call the component makes on mount
  await page.route("**/api/users/42", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 42, name: "Ada Lovelace", role: "admin" }),
    })
  );

  const component = await mount(<UserCard userId={42} />);
  await expect(component.getByRole("heading")).toHaveText("Ada Lovelace");
  await expect(component.getByTestId("role-badge")).toHaveText("admin");
});

test("shows skeleton while loading", async ({ mount, page }) => {
  // Never resolve the route — test the loading state
  await page.route("**/api/users/99", (_route) => { /* hang */ });

  const component = await mount(<UserCard userId={99} />);
  await expect(component.getByTestId("skeleton")).toBeVisible();
});
```

## Accessibility and Visual Snapshot Testing

```tsx
// src/components/Modal.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import { Modal } from "./Modal";

test("is accessible when open", async ({ mount, page }) => {
  const component = await mount(
    <Modal open title="Confirm Delete">
      <p>This action cannot be undone.</p>
    </Modal>
  );

  // ARIA role check
  await expect(component.getByRole("dialog")).toBeVisible();
  await expect(component.getByRole("dialog")).toHaveAttribute("aria-modal", "true");

  // Focus is trapped inside the modal
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.tagName);
  expect(["BUTTON", "INPUT", "A"]).toContain(focused);
});

test("visual snapshot matches baseline", async ({ mount }) => {
  const component = await mount(
    <Modal open title="Snapshot Test">
      <p>Content</p>
    </Modal>
  );
  await expect(component).toHaveScreenshot("modal-open.png");
});
```

## CI Integration with GitHub Actions

```yaml
# .github/workflows/ct.yml
name: Component Tests
on: [push, pull_request]
jobs:
  ct:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: "pnpm" }
      - run: pnpm install --frozen-lockfile
      - run: pnpm playwright install --with-deps chromium
      - run: pnpm test:ct
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-ct-report
          path: playwright-report/
```

## Anti-patterns
- Do not use `@playwright/experimental-ct-react` for tests that need the Pages Functions runtime
  (Workers, D1, KV); use `wrangler pages dev` + standard Playwright E2E for those.
- Do not hardcode `localhost:3100` in component tests; the port is managed by `ctPort` in config.
- Do not rely on `page.goto()` inside a component test; the fixture `mount` is the entry point,
  not navigation.
- Do not mix component tests and E2E tests in the same config file; they need separate configs.

## Gotchas
- Snapshot baselines are stored per-OS; running `toHaveScreenshot` locally on macOS then in a
  Linux CI container will produce mismatches. Generate baselines in CI using
  `playwright test --update-snapshots`.
- Hot module replacement in the CT Vite server can cause stale state between test runs if a test
  modifies a module-level variable; use `beforeEach` resets.
- `@playwright/experimental-ct-react` is still experimental; the API may change with Playwright
  minor releases. Pin the Playwright version in `package.json`.
- The CT iframe does not inherit the Pages `_headers` or `_redirects` files; test those separately.

## Verification

```bash
# Run all component tests headlessly
pnpm test:ct

# Run in headed mode to watch interactions
pnpm playwright test -c playwright-ct.config.ts --headed

# Update visual snapshots
pnpm playwright test -c playwright-ct.config.ts --update-snapshots

# Show HTML report
pnpm playwright show-report
```

## Related
- `playwright-e2e-workers-wrangler-dev.md` — full E2E against a running Pages/Workers app
- `playwright-ui-mode-workers-debugging.md` — Playwright UI mode for debugging test failures
- `storybook-cloudflare-pages-components.md` — visual component catalogue for Pages
- `vite-cloudflare-workers-dev-mode.md` — Vite dev server configuration

## Sources
- https://playwright.dev/docs/test-components
- https://developers.cloudflare.com/pages/
- https://vitejs.dev/guide/
- https://github.com/microsoft/playwright/tree/main/packages/playwright-ct-react
