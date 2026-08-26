# test-data-builders

**Issue:** Creating readable, maintainable test data without massive object literals
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests with `{ id: 1, name: "Alice", email: "alice@test.com", role: "admin", createdAt: ..., updatedAt: ..., ... }` in every test are hard to read and brittle.

## Pattern / Solution
```ts
// Builder pattern
class UserBuilder {
  private user: User = {
    id: "default-id",
    name: "Test User",
    email: "test@example.com",
    role: "user",
    active: true,
    createdAt: new Date("2026-01-01"),
  };

  withName(name: string) { return Object.assign(this, { user: { ...this.user, name } }); }
  withRole(role: Role) { return Object.assign(this, { user: { ...this.user, role } }); }
  inactive() { return Object.assign(this, { user: { ...this.user, active: false } }); }
  build(): User { return { ...this.user }; }
}

// Usage
const admin = new UserBuilder().withRole("admin").build();
const inactiveUser = new UserBuilder().withName("Bob").inactive().build();

// Simpler with factory function
const makeUser = (overrides: Partial<User> = {}): User => ({
  id: "test-id",
  name: "Alice",
  email: "alice@example.com",
  role: "user",
  ...overrides,
});
```

## Gotchas
- Builder should have sensible defaults — tests only specify what matters for that test
- Don't reuse builders across tests if mutations are possible
- Use `faker` for unique values like emails

## Related
- `faker-js-test-data.md`
- `test-fixtures-patterns.md`
- `factory-pattern-tests.md`
