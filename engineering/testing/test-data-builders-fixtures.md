# test-data-builders-fixtures

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Every test file constructs its own raw object literals for
`User`, `Order`, or `Product`. Adding a required field to
the type breaks dozens of tests at once, and the boilerplate
in each test drowns the one field that actually matters.

## Context

Test data builders centralise object construction so tests
declare only the fields relevant to the scenario. Paired
with `faker.js` for realistic seed data and isolated D1
database instances for integration tests, the pattern keeps
suites readable, resilient to schema changes, and free of
cross-test pollution.

## The Builder Pattern for Complex Objects

```ts
// src/test/builders/user.builder.ts
import { faker } from '@faker-js/faker';
import type { User } from '../../types';

export class UserBuilder {
  private data: User = {
    id:        faker.string.uuid(),
    name:      faker.person.fullName(),
    email:     faker.internet.email(),
    role:      'viewer',
    active:    true,
    createdAt: new Date(),
  };

  withRole(role: User['role']): this {
    this.data.role = role; return this;
  }
  inactive(): this {
    this.data.active = false; return this;
  }
  build(): User { return structuredClone(this.data); }
}

// Usage
const admin = new UserBuilder().withRole('admin').build();
const ghost = new UserBuilder().inactive().build();
```

## Faker.js for Realistic Seed Data

```bash
npm install -D @faker-js/faker
```

```ts
import { faker } from '@faker-js/faker';

// Deterministic output — pin in beforeAll for CI
faker.seed(Number(process.env.SEED ?? 42));

const product = {
  id:    faker.string.uuid(),
  title: faker.commerce.productName(),
  price: faker.commerce.price({ min: 1, max: 999 }),
  stock: faker.number.int({ min: 0, max: 500 }),
  sku:   faker.string.alphanumeric(8).toUpperCase(),
};
```

Common namespaces: `faker.person`, `faker.internet`,
`faker.location`, `faker.date`, `faker.commerce`.
Use `faker.locale = 'de'` for locale-specific formats.

## Factory Functions vs Fixture Files

| Approach       | Strengths           | Weaknesses          |
|----------------|---------------------|---------------------|
| Builder class  | Fluent, discoverable| Verbose for simple  |
| Factory fn     | Light, tree-shakeable| Less discoverable  |
| JSON fixture   | Static, versioned   | No dynamic data     |
| DB seed script | Realistic relational| Slow, hard to isolate|

Factory function (lighter than a class):

```ts
export function makeOrder(
  overrides: Partial<Order> = {}
): Order {
  return {
    id:        faker.string.uuid(),
    userId:    faker.string.uuid(),
    total:     faker.number.float({ min: 1, max: 9999 }),
    status:    'pending',
    items:     [],
    createdAt: new Date(),
    ...overrides,
  };
}
```

Use factory functions for simple value objects; reserve the
builder class for deeply nested or polymorphic models.

## D1 Test Database Seeding

Configure Miniflare's in-process D1 binding in Vitest with
one isolated database per worker:

```ts
// vitest.config.ts
export default defineConfig({
  test: {
    environment:        'miniflare',
    environmentOptions: { d1Databases: ['DB'] },
    poolOptions: { threads: { singleThread: false } },
    setupFiles:         ['src/test/d1-setup.ts'],
  },
});
```

```ts
// src/test/d1-setup.ts
import { env } from 'cloudflare:test';

export async function seedD1(users: User[]) {
  const db   = env.DB;
  const stmt = db.prepare(
    'INSERT INTO users (id, name, email, role) VALUES (?,?,?,?)'
  );
  await db.prepare('DELETE FROM users').run();
  for (const u of users)
    await stmt.bind(u.id, u.name, u.email, u.role).run();
}
```

Call `seedD1` in `beforeEach`, never `beforeAll`, so each
test starts from a known state. A `DELETE` in one parallel
worker removes rows another test expects, causing spurious
failures. `singleThread: false` gives each Vitest worker
its own Miniflare process; run migrations in `globalSetup`
so the schema exists before any worker spawns.

## Anti-patterns

- Sharing an object reference across tests — one mutation
  poisons later tests silently.
- Seeding from production data dumps — PII leaks into
  build logs; use faker-generated data only.
- JSON fixtures for objects with foreign-key relations —
  IDs drift out of sync when the schema changes.
- Defaulting optional fields to `undefined` in factories
  — type errors surface at runtime, not at the call site.

## Gotchas

- `structuredClone` does not deep-clone class instances
  such as `Date` faithfully in all runtimes; verify the
  round-tripped value is still a `Date`, not a plain object.
- `faker.seed()` is global state; seeding in one factory
  file affects all faker calls in the same worker process.
- Builder classes are not safe to share across workers;
  instantiate a fresh builder per test, never once globally.

## Verification

```bash
# Confirm builder types compile
npx tsc --noEmit

# Run D1 integration tests in isolated workers
npx vitest run src/test/integration/ --reporter=verbose
```

All tests should pass independently of execution order,
and no test should fail only when run in parallel.

## Related

- `testing/faker-js-test-data.md`
- `testing/factory-pattern-tests.md`
- `testing/test-fixtures-patterns.md`
- `testing/d1-testing-local.md`
- `testing/database-seeding-tests.md`

## Source URLs (verified 2026-08-17)

- https://fakerjs.dev/guide/
- https://developers.cloudflare.com/d1/testing/
- https://miniflare.dev/testing/vitest
- https://vitest.dev/config/#environment
- https://refactoring.guru/design-patterns/builder
