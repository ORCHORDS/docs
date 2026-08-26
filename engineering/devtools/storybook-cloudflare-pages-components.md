# storybook-cloudflare-pages-components

**Issue:** Component development for example project happens inside the full
Next.js app, making it slow to iterate on UI states, impossible to
document edge cases, and difficult to test mobile viewports in isolation.
Storybook deployed to Cloudflare Pages gives the team a living component
catalogue at a public URL, with interaction tests, accessibility checks,
and mobile viewport previews — without a separate hosting provider.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
# Current state: component testing requires running the full app
pnpm dev   # starts Next.js dev server, loads DB, loads Worker…
# Then navigate 4 pages to reach the component under test
# Mobile testing: open Chrome DevTools, resize, refresh

# No documentation of what props each component accepts
# No regression test for "what does the error state look like"
# Accessibility failures found only in production user reports
```

UI regressions are caught late, in QA or in production. Component
states (loading, error, empty, overflow) are not systematically tested.
The design team has no reference for what components exist.

## Context

Storybook is a component development environment that runs independently
of the application. Each "story" is a function that renders a component
in a specific state. Storybook 8 ships with a Vite builder, interaction
tests via `@storybook/test`, and an accessibility addon that runs Axe
checks on every story. The `@storybook/addon-viewport` addon provides
presets for mobile screen sizes. Deploying Storybook to Cloudflare Pages
gives the team a permanent, indexed URL for every build with zero extra
infrastructure.

## Installation (pnpm monorepo)

```bash
# In the UI package or web app where components live
cd apps/web
pnpm dlx storybook@latest init --builder vite --type nextjs

# Or in a dedicated packages/ui package
cd packages/ui
pnpm dlx storybook@latest init --builder vite --type react
```

Install addons:

```bash
pnpm add -D \
  @storybook/addon-a11y \
  @storybook/addon-interactions \
  @storybook/addon-viewport \
  @storybook/test \
  --filter @example project/ui
```

## .storybook/main.ts

```ts
import type { StorybookConfig } from "@storybook/nextjs-vite";

const config: StorybookConfig = {
  stories: [
    "../src/**/*.stories.@(js|jsx|ts|tsx)",
    "../src/**/*.mdx",
  ],
  addons: [
    "@storybook/addon-essentials",
    "@storybook/addon-a11y",
    "@storybook/addon-interactions",
    "@storybook/addon-viewport",
  ],
  framework: {
    name: "@storybook/nextjs-vite",
    options: {},
  },
  docs: {
    autodocs: "tag",
  },
  staticDirs: ["../public"],
};

export default config;
```

## .storybook/preview.ts

```ts
import type { Preview } from "@storybook/react";
import { INITIAL_VIEWPORTS } from "@storybook/addon-viewport";
import "../src/styles/globals.css";

const example project_VIEWPORTS = {
  iphone14: {
    name: "iPhone 14",
    styles: { width: "390px", height: "844px" },
    type: "mobile",
  },
  iphone14ProMax: {
    name: "iPhone 14 Pro Max",
    styles: { width: "430px", height: "932px" },
    type: "mobile",
  },
  pixel7: {
    name: "Pixel 7",
    styles: { width: "412px", height: "915px" },
    type: "mobile",
  },
  ipadPro: {
    name: "iPad Pro 12.9\"",
    styles: { width: "1024px", height: "1366px" },
    type: "tablet",
  },
};

const preview: Preview = {
  parameters: {
    viewport: {
      viewports: { ...INITIAL_VIEWPORTS, ...example project_VIEWPORTS },
      defaultViewport: "responsive",
    },
    backgrounds: {
      default: "light",
      values: [
        { name: "light", value: "#ffffff" },
        { name: "dark", value: "#0a0a0a" },
      ],
    },
    a11y: {
      config: {
        rules: [
          { id: "color-contrast", enabled: true },
          { id: "label", enabled: true },
        ],
      },
    },
    controls: { matchers: { color: /(background|color)$/i } },
  },
};

export default preview;
```

## Writing stories with interaction tests

```ts
// src/components/SessionCard/SessionCard.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { expect, userEvent, within } from "@storybook/test";
import { SessionCard } from "./SessionCard";

const meta: Meta<typeof SessionCard> = {
  component: SessionCard,
  title: "Components/SessionCard",
  tags: ["autodocs"],
  parameters: {
    viewport: { defaultViewport: "iphone14" },
  },
};
export default meta;
type Story = StoryObj<typeof SessionCard>;

export const Default: Story = {
  args: {
    sessionId: "sess_abc123",
    userHandle: "@jane",
    startedAt: new Date("2026-08-22T10:00:00Z"),
    isActive: true,
  },
};

export const Expired: Story = {
  args: {
    ...Default.args,
    isActive: false,
    expiredAt: new Date("2026-08-22T11:00:00Z"),
  },
};

export const LongHandle: Story = {
  args: {
    ...Default.args,
    userHandle: "@this-is-a-very-long-handle-that-should-truncate",
  },
  parameters: {
    // Test both mobile and desktop truncation
    viewport: { defaultViewport: "responsive" },
  },
};

// Interaction test: expand session details on click
export const ExpandOnClick: Story = {
  args: Default.args,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const card = canvas.getByRole("article");
    await userEvent.click(card);
    await expect(
      canvas.getByText(/session details/i)
    ).toBeVisible();
  },
};
```

## Mobile viewport stories best practice

Group mobile-specific stories with a viewport parameter so the Storybook
sidebar makes the context clear:

```ts
export const MobileDefault: Story = {
  name: "Default (iPhone 14)",
  args: Default.args,
  parameters: {
    viewport: { defaultViewport: "iphone14" },
    chromatic: { viewports: [390, 768, 1280] }, // for visual regression
  },
};

export const MobileDark: Story = {
  name: "Default (iPhone 14 / Dark)",
  args: Default.args,
  parameters: {
    viewport: { defaultViewport: "iphone14" },
    backgrounds: { default: "dark" },
  },
};
```

## Accessibility addon workflow

The `@storybook/addon-a11y` panel runs Axe on the currently rendered
story. For CI, run headless Axe checks with the Storybook test runner:

```bash
pnpm add -D @storybook/test-runner axe-playwright --filter @example project/ui
```

```json
// package.json (packages/ui)
{
  "scripts": {
    "test-storybook": "test-storybook --url http://localhost:6006"
  }
}
```

```ts
// .storybook/test-runner.ts
import { checkA11y, injectAxe } from "axe-playwright";
import type { TestRunnerConfig } from "@storybook/test-runner";

const config: TestRunnerConfig = {
  async preVisit(page) {
    await injectAxe(page);
  },
  async postVisit(page) {
    await checkA11y(page, "#storybook-root", {
      detailedReport: true,
      detailedReportOptions: { html: true },
    });
  },
};
export default config;
```

## Build and deploy to Cloudflare Pages

```json
// packages/ui/package.json
{
  "scripts": {
    "build-storybook": "storybook build -o storybook-static"
  }
}
```

```toml
# Cloudflare Pages settings (wrangler.toml or Pages dashboard)
# Project name: example project-storybook
# Build command: pnpm --filter @example project/ui build-storybook
# Build output directory: packages/ui/storybook-static
# Root directory: /  (monorepo root)
```

GitHub Actions deploy:

```yaml
# .github/workflows/storybook.yml
name: Storybook

on:
  push:
    branches: [main]
    paths:
      - "packages/ui/src/**"
      - "packages/ui/.storybook/**"
      - "packages/ui/package.json"

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter @example project/ui build-storybook
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy packages/ui/storybook-static --project-name=example project-storybook
```

The deploy only triggers when UI source files change — not on every
backend commit — keeping Cloudflare Pages build minutes efficient.

## Anti-patterns

- **Importing the Worker or D1 binding inside a story** — Storybook
  runs in the browser; mock Worker calls with `@storybook/test`'s
  `fn()` or MSW.
- **No `paths` filter on the Storybook workflow** — every push to main
  deploys Storybook even when only the Worker changed.
- **Story per file instead of story per state** — one story file should
  cover all visual states (default, loading, error, empty, overflow).
- **Skipping accessibility stories** — if a component has a11y issues,
  the addon panel shows them; act on them before merging.

## Gotchas

- `@storybook/nextjs-vite` (Storybook 9) requires Vite 6+; confirm
  `vite` version in `packages/ui/package.json` before upgrading.
- Storybook's Vite builder does not run Next.js middleware; mock
  `next/navigation` and `next/headers` in `.storybook/preview.ts`.
- `storybook build` emits to `storybook-static/` by default; Cloudflare
  Pages must be pointed at the exact output directory.
- The test-runner needs a running Storybook server (`storybook dev`)
  or a previously built static Storybook (`http-server storybook-static`).

## Verification

```bash
# Local dev
pnpm --filter @example project/ui storybook

# Run interaction tests
pnpm --filter @example project/ui build-storybook
npx http-server packages/ui/storybook-static -p 6006 &
pnpm --filter @example project/ui test-storybook

# Check Pages deploy
wrangler pages deployment list --project-name=example project-storybook
# Visit: https://example project-storybook.pages.dev
```

## Related

- `documentation/categories/devtools/vitest-workers-miniflare-testing-setup.md`
- `documentation/categories/devtools/lighthouse-ci-performance-budget-github-actions.md`
- `documentation/categories/devtools/typescript-cloudflare-workers-strict.md`
- `documentation/categories/devtools/turborepo-cloudflare-workers-pipeline.md`
- `documentation/categories/devtools/remote-debugging-mobile-web.md`

## Sources

- https://storybook.js.org/docs/get-started/install
- https://storybook.js.org/docs/writing-stories/play-function
- https://storybook.js.org/docs/writing-tests/accessibility-testing
- https://storybook.js.org/docs/essentials/viewport
- https://developers.cloudflare.com/pages/framework-guides/deploy-a-storybook-site/
- https://github.com/cloudflare/wrangler-action
