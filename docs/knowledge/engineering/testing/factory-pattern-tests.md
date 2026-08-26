# factory-pattern-tests

**Issue:** Using factory functions to generate test data with minimal boilerplate
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Builder pattern is verbose for simple data. Factory functions are a lighter alternative.

## Pattern / Solution
```ts
// factories/user.ts
import { faker } from "@faker-js/faker";
import type { User } from "../types";

let idCounter = 0;

export function createUser(overrides: Partial<User> = {}): User {
  return {
    id: String(++idCounter),
    name: faker.person.fullName(),
    email: faker.internet.email(),
    role: "user",
    active: true,
    createdAt: new Date(),
    ...overrides,
  };
}

export function createUsers(count: number, overrides: Partial<User> = {}): User[] {
  return Array.from({ length: count }, () => createUser(overrides));
}

// Usage in tests
it("shows all active users", () => {
  const users = [
    createUser({ active: true }),
    createUser({ active: false }),
    createUser({ active: true }),
  ];
  const result = filterActive(users);
  expect(result).toHaveLength(2);
});
```

## Gotchas
- Reset counter between test suites if IDs need to be predictable
- Factories should be deterministic when given the same seed
- Don't share factory state across parallel test workers

## Related
- `test-data-builders.md`
- `faker-js-test-data.md`
- `test-fixtures-patterns.md`
