# playwright-test-isolation

**Issue:** Playwright tests share browser state (cookies, localStorage) across tests when not properly isolated, causing flaky order-dependent failures
**Date:** 2026-08-11
**Status:** documented

## Symptom
Tests pass individually but fail when run in suite. A test that depends on being logged out fails because the previous test left a session cookie. Test order in CI differs from local and produces different results.

## Root cause
Playwright reuses browser contexts between tests in the same worker by default when using `storageState`. If a test modifies auth state, localStorage, or cookies without cleanup, subsequent tests inherit the dirty state.

## Fix
Use `test.use({ storageState: undefined })` for tests that must start unauthenticated, or create a fresh browser context per test:
```ts
// playwright.config.ts
export default defineConfig({
  use: {
    // Each test gets a fresh context
    storageState: undefined,
  },
});

// Or per-test
test.use({ storageState: 'tests/auth.json' });
test('logged-in page', async ({ page }) => { /* ... */ });
```
Use `page.context().clearCookies()` in `beforeEach` for shared contexts.

## Detection
```
grep -rn "storageState\|clearCookies\|localStorage" tests/ --include="*.ts"
```
Tests that set `storageState` at the file level affect all tests in that file.

## Related
- `vitest-module-mock-hoisting.md`
