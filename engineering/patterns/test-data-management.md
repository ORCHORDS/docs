# test-data-management

**Issue:** Test data — fixtures, factories, isolation
**Date:** 2026-08-09
**Status:** documented

## Symptom
You write a test. It depends on a user with id 'u_123'.
You run the test. It passes. Another engineer runs the
test. It fails because 'u_123' was deleted. The test is
flaky.

## Root cause
**Test data is shared, mutable, and not isolated.** A test
that depends on a specific record is fragile.

**Source:** Various testing guides.

## The "factory" pattern

```ts
// test/factories.ts
import { faker } from '@faker-js/faker';

let counter = 0;

export function makeUser(overrides: Partial<User> = {}): User {
  counter++;
  return {
    id: `u_test_${counter}`,
    email: faker.internet.email(),
    displayName: faker.person.fullName(),
    role: 'viewer',
    plan: 'free',
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

export function makePost(overrides: Partial<Post> = {}): Post {
  counter++;
  return {
    id: `p_test_${counter}`,
    title: faker.lorem.sentence(),
    body: faker.lorem.paragraph(),
    authorId: 'u_test_1',
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}
```

Each call creates a new instance with a unique ID. No
sharing.

## The "fixture" pattern

For static data that's used across tests:
```ts
// test/fixtures.ts
export const testUsers: Record<string, User> = {
  alice: { id: 'u_alice', email: 'alice@test.com', displayName: 'Alice' },
  bob: { id: 'u_bob', email: 'bob@test.com', displayName: 'Bob' },
  admin: { id: 'u_admin', email: 'admin@test.com', displayName: 'Admin', role: 'admin' },
};
```

Use for read-only data; use factories for write tests.

## The "isolation" pattern

For DB tests, use a per-test database:
```ts
beforeEach(async () => {
  // Create a fresh test DB
  await migrateTestDb();
  await seedTestData();
});

afterEach(async () => {
  // Drop the test DB
  await dropTestDb();
});
```

Each test starts with a clean DB.

## The "transaction rollback" pattern

For DB tests, wrap each test in a transaction:
```ts
beforeEach(async () => {
  await db.exec('BEGIN');
});

afterEach(async () => {
  await db.exec('ROLLBACK');
});
```

The test's changes are rolled back; the DB is unchanged.

For D1, transactions are limited. Use a per-test DB.

## The "seed" pattern

For tests that need specific data:
```ts
// test/seed.ts
export async function seedTestData(env: Env): Promise<void> {
  const users = [
    { id: 'u_1', email: 'alice@test.com', displayName: 'Alice' },
    { id: 'u_2', email: 'bob@test.com', displayName: 'Bob' },
  ];

  for (const user of users) {
    await env.DB!.prepare(
      `INSERT INTO users (id, email, displayName) VALUES (?, ?, ?)`
    ).bind(user.id, user.email, user.displayName).run();
  }
}
```

The seed is run before the test suite.

## The "mock" pattern

For external services, mock them:
```ts
import { vi } from 'vitest';

vi.mock('stripe', () => ({
  default: vi.fn().mockImplementation(() => ({
    charges: {
      create: vi.fn().mockResolvedValue({ id: 'ch_test', status: 'succeeded' }),
    },
  })),
}));
```

The mock is configured once; tests use the mock.

## The "test data in D1" pattern

For CF Workers tests, use a separate D1:
```toml
# wrangler.test.toml
[[d1_databases]]
binding = "DB"
database_name = "test-db"
database_id = "test-db-id"
```

The test uses a different DB.

## The "test data in DOs" pattern

For DOs, create per-test instances:
```ts
beforeEach(async () => {
  // Each test gets a fresh DO
  const id = env.MY_DO.newUniqueId();
  const stub = env.MY_DO.get(id);
  // ... use the stub
});
```

The DO is fresh for each test.

## The "test data" naming convention

Use `test_` prefix to distinguish from production data:
```ts
const user = { id: 'u_test_abc', email: 'test_abc@example.com', ... };
```

A search for `test_` finds all test data.

## The "test data lifecycle"

```ts
describe('UserService', () => {
  let env: Env;

  beforeAll(async () => {
    // Set up once for the suite
    env = await createTestEnv();
  });

  beforeEach(async () => {
    // Reset for each test
    await resetTestDb(env);
  });

  afterAll(async () => {
    // Clean up
    await destroyTestEnv(env);
  });

  test('getUser returns the user', async () => {
    const user = makeUser({ id: 'u_1' });
    await env.DB!.prepare(`INSERT INTO users ...`).bind(...).run();

    const result = await userService.getById('u_1', ctx(env));
    expect(result).toEqual(user);
  });
});
```

## The "data generation" libraries

For realistic test data:
- **faker.js:** Names, emails, addresses, etc.
- **chance.js:** Random data
- **@ngneat/falso:** Faster alternative to faker

```ts
import { faker } from '@faker-js/faker';

const user = makeUser({
  email: faker.internet.email(),
  displayName: faker.person.fullName(),
  age: faker.number.int({ min: 18, max: 80 }),
});
```

The data is random but realistic.

## The "PII" in test data

For GDPR / CCPA, be careful with test data:
- ❌ Don't use real customer data
- ❌ Don't use real names + emails
- ✅ Use fake data (faker)
- ✅ Use the data deletion tools (test cleanup)

For tests that need production-like data:
- **Anonymize:** Replace names with hashes
- **Mask:** Replace sensitive fields with `***`
- **Generate:** Use realistic fake data

## The "test data size"

For performance tests, you need real-scale data:
```ts
// 1M users for load testing
const users = Array.from({ length: 1_000_000 }, () => makeUser());
await bulkInsert(users);
```

A small dataset doesn't show perf issues.

## The "data assertion" pattern

For tests that depend on data:
```ts
test('listUsers returns the seeded users', async () => {
  await seedTestData(env);

  const result = await userService.list(ctx(env));

  expect(result).toHaveLength(3);
  expect(result[0].email).toBe('alice@test.com');
});
```

The test seeds + asserts on the data.

## Verification
- **Test:** Each test is isolated
- **Live:** Tests run in parallel without interference
- **Audit:** Quarterly review of test data

## Gotchas
- **The "shared mutable data" anti-pattern.** Tests that
  share data are flaky. Use factories.
- **The "production data in tests" anti-pattern.** Use fake
  data; never use production data.
- **The "test depends on time" anti-pattern.** Mock the
  time; don't depend on real time.
- **The "test depends on network" anti-pattern.** Mock the
  network; don't make real calls.
- **The "test data left in DB" anti-pattern.** Clean up
  after each test; don't leave data.
- **The "test data with PII" anti-pattern.** Use fake data
  to avoid GDPR issues.

## Related
- `unit-testing-patterns.md`
- `integration-testing-cf.md` (later)
- `e2e-testing-patterns.md`
- `test-pyramid.md`
- faker.js: https://fakerjs.dev/
- chance.js: https://chancejs.com/
- testcontainers: https://testcontainers.com/
