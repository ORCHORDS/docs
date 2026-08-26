# playwright-api-testing

**Issue:** Using Playwright's request context for API testing alongside browser tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Writing separate API tests in Supertest and browser tests in Playwright requires maintaining two test setups. Playwright's `request` fixture handles both.

## Pattern / Solution
```ts
import { test, expect } from "@playwright/test";

test("POST /api/users creates user", async ({ request }) => {
  const response = await request.post("/api/users", {
    data: { name: "Alice", email: "alice@example.com" },
  });

  expect(response.status()).toBe(201);
  const body = await response.json();
  expect(body).toMatchObject({ name: "Alice", id: expect.any(String) });
});

test("GET /api/users returns list", async ({ request }) => {
  const response = await request.get("/api/users");
  expect(response.ok()).toBeTruthy();
  const users = await response.json();
  expect(Array.isArray(users)).toBe(true);
});

// Reuse auth context
const authContext = await request.newContext({
  extraHTTPHeaders: { Authorization: `Bearer ${token}` },
});
```

## Gotchas
- `request` context does not share cookies with `page` context by default
- Use `storageState` to share auth between request and browser contexts
- Playwright API testing does not replace dedicated API test suites for complex scenarios

## Related
- `api-testing-supertest.md`
- `playwright-authentication-state.md`
