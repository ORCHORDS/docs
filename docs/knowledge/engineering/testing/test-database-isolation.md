# test-database-isolation

**Issue:** Preventing tests from interfering with each other through shared database state
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Test A creates a user. Test B counts users and gets the wrong number because Test A's data persists.

## Pattern / Solution
Strategy 1 — Transaction rollback (fastest):
```ts
let txn: Knex.Transaction;

beforeEach(async () => { txn = await db.transaction(); });
afterEach(async () => { await txn.rollback(); });

it("creates user", async () => {
  await userRepo.create({ name: "Alice" }, txn);
  const users = await userRepo.findAll(txn);
  expect(users).toHaveLength(1); // only visible in this transaction
});
```

Strategy 2 — Schema-per-test (true isolation, slower):
```ts
beforeEach(async () => {
  const schema = `test_${Date.now()}`;
  await db.raw(`CREATE SCHEMA ${schema}`);
  await runMigrations(schema);
  currentSchema = schema;
});

afterEach(async () => {
  await db.raw(`DROP SCHEMA ${currentSchema} CASCADE`);
});
```

Strategy 3 — Truncate in beforeEach (simple, fast enough for small datasets).

## Gotchas
- Transactions don't work across multiple DB connections
- Schema isolation adds 200-500ms per test — use transaction rollback for unit-style integration tests
- Always clean up — leaked schemas accumulate in development DBs

## Related
- `transactional-test-rollback.md`
- `database-seeding-tests.md`
- `integration-test-database.md`
