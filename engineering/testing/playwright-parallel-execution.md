# playwright-parallel-execution

**Issue:** Running Playwright tests in parallel without conflicts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests interfere with each other when run in parallel because they share database state or use the same test accounts.

## Pattern / Solution
```ts
// Make tests independent — each creates its own data
test("user can update profile", async ({ page, request }) => {
  // Create isolated test user via API
  const user = await request.post("/api/test/users", {
    data: { email: `test-${Date.now()}@example.com`, password: "pass" },
  });
  const { id, email } = await user.json();

  // Login and test
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  // ...

  // Cleanup
  await request.delete(`/api/test/users/${id}`);
});
```

`playwright.config.ts`:
```ts
fullyParallel: true,
workers: process.env.CI ? 4 : "50%",
```

Use `test.describe.configure({ mode: "serial" })` for tests that must run sequentially within a file.

## Gotchas
- Never share mutable state between parallel tests
- Database tests need isolated schemas or transaction rollback
- `workers: 1` in CI is safer but slower — tune based on resources

## Related
- `playwright-setup.md`
- `test-database-isolation.md`
- `ci-test-parallelization.md`
