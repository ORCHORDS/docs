# playwright-network-interception

**Issue:** Mocking API responses and blocking requests in Playwright tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
E2e tests that hit real APIs are slow and depend on external state. Network interception makes tests deterministic.

## Pattern / Solution
```ts
import { test, expect } from "@playwright/test";

test("displays user from API", async ({ page }) => {
  // Mock API response
  await page.route("**/api/users/1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, name: "Alice", email: "alice@example.com" }),
    });
  });

  await page.goto("/users/1");
  await expect(page.getByText("Alice")).toBeVisible();
});

test("handles API error gracefully", async ({ page }) => {
  await page.route("**/api/users/*", (route) =>
    route.fulfill({ status: 500, body: "Internal Server Error" })
  );

  await page.goto("/users/1");
  await expect(page.getByRole("alert")).toContainText("Something went wrong");
});

// Block analytics and tracking
await page.route("**/{analytics,tracking}/**", (route) => route.abort());
```

## Gotchas
- Routes are matched with glob patterns — `**` crosses path segments
- `route.continue()` passes through with optional modifications
- Set routes before `page.goto()` to intercept initial load requests

## Related
- `playwright-setup.md`
- `mock-server-msw.md`
