# playwright-authentication-state

**Issue:** Reusing browser authentication state across tests to avoid repeated logins
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Each test performing a full login sequence adds 2-5 seconds per test. With 100 tests, that is 3-8 minutes wasted.

## Pattern / Solution
```ts
// e2e/auth.setup.ts
import { test as setup, expect } from "@playwright/test";
import path from "path";

const authFile = path.join(__dirname, ".auth/user.json");

setup("authenticate", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("user@example.com");
  await page.getByLabel("Password").fill("password123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("/dashboard");
  await page.context().storageState({ path: authFile });
});
```

`playwright.config.ts`:
```ts
projects: [
  { name: "setup", testMatch: /auth\.setup\.ts/ },
  {
    name: "authenticated",
    use: { storageState: "e2e/.auth/user.json" },
    dependencies: ["setup"],
  },
],
```

## Gotchas
- Add `.auth/` to `.gitignore` — contains session tokens
- Auth state expires — re-run setup project when sessions expire
- Use different auth files for different user roles

## Related
- `playwright-fixtures.md`
- `playwright-setup.md`
