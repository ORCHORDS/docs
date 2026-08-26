# playwright-setup

**Issue:** Setting up Playwright for end-to-end testing with TypeScript
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Playwright needs correct configuration for timeouts, base URL, retries, and parallelism to work reliably in CI.

## Pattern / Solution
```bash
npm init playwright@latest
```

`playwright.config.ts`:
```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html"], ["junit", { outputFile: "results.xml" }]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
  },
});
```

## Gotchas
- `fullyParallel: true` requires tests to be independent
- `retries: 2` in CI masks flaky tests — fix root causes
- `trace: "on-first-retry"` gives full trace for failed tests

## Related
- `playwright-page-object-model.md`
- `playwright-fixtures.md`
- `playwright-parallel-execution.md`
