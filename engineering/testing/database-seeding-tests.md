# database-seeding-tests

**Issue:** Seeding database with test data before integration tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Integration tests that query the database need consistent starting state. Ad-hoc inserts in each test file are duplicated and fragile.

## Pattern / Solution
```ts
// seeds/test/users.ts
import { db } from "../../src/db";

export async function seedUsers() {
  return db("users").insert([
    { id: "user-1", name: "Alice", email: "alice@example.com", role: "admin" },
    { id: "user-2", name: "Bob", email: "bob@example.com", role: "user" },
  ]);
}

export async function clearUsers() {
  return db("users").truncate();
}

// In test file
beforeEach(async () => {
  await clearUsers();
  await seedUsers();
});

afterAll(async () => {
  await clearUsers();
  await db.destroy();
});
```

With Knex seed files:
```bash
npx knex seed:run --specific test_users.ts
```

## Gotchas
- Truncate before seed, not after — leaves DB clean after debugging
- Foreign key constraints may require truncation in dependency order
- Use transactions instead of truncation when possible for speed

## Related
- `test-database-isolation.md`
- `transactional-test-rollback.md`
- `integration-test-database.md`
