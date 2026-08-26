# test-fixtures-patterns

**Issue:** Organizing test fixtures for reuse without coupling tests together
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests share fixture data defined in `beforeAll`, causing test interdependencies and order-sensitive failures.

## Pattern / Solution
```ts
// fixtures/users.ts — static fixtures
export const fixtures = {
  admin: { id: "admin-1", name: "Admin", role: "admin" } as User,
  regularUser: { id: "user-1", name: "Alice", role: "user" } as User,
  inactiveUser: { id: "user-2", name: "Bob", role: "user", active: false } as User,
};

// In tests — use fixture object (immutable)
it("allows admin to delete users", () => {
  const policy = new AuthPolicy();
  expect(policy.canDelete(fixtures.admin)).toBe(true);
  expect(policy.canDelete(fixtures.regularUser)).toBe(false);
});

// Playwright fixtures
test.use({
  storageState: "e2e/.auth/admin.json",
});
```

Fixture file naming:
- `fixtures/` — static data
- `factories/` — dynamic builders
- `mocks/` — mock service implementations

## Gotchas
- Never mutate fixture objects — spread them when needing customization
- Keep fixtures close to the tests that use them
- Database fixtures should be inserted fresh per test, not per suite

## Related
- `test-data-builders.md`
- `database-seeding-tests.md`
- `factory-pattern-tests.md`
