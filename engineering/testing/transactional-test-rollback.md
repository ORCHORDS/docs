# transactional-test-rollback

**Issue:** Rolling back database transactions in tests to avoid persistent state
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Truncating tables between tests is slow. Rolling back a transaction is near-instant and leaves the DB clean.

## Pattern / Solution
```ts
// With Prisma
import { prisma } from "../client";

let tx: Prisma.TransactionClient;

beforeEach(async () => {
  // Prisma doesn't expose raw transactions easily — use pg directly
});

// With pg (node-postgres) directly
import { Pool } from "pg";
const pool = new Pool({ connectionString: process.env.TEST_DATABASE_URL });

let client: PoolClient;
beforeEach(async () => {
  client = await pool.connect();
  await client.query("BEGIN");
});

afterEach(async () => {
  await client.query("ROLLBACK");
  client.release();
});

it("inserts a row", async () => {
  await client.query("INSERT INTO users (name) VALUES ($1)", ["Alice"]);
  const result = await client.query("SELECT * FROM users WHERE name = $1", ["Alice"]);
  expect(result.rows).toHaveLength(1);
});
```

For Knex:
```ts
beforeEach(async () => { trx = await knex.transaction(); });
afterEach(async () => { await trx.rollback(); });
```

## Gotchas
- Rollback only works if all test queries use the same connection/transaction
- Auto-commit statements (DDL, TRUNCATE) cannot be rolled back in Postgres
- Nested transactions require SAVEPOINTs

## Related
- `test-database-isolation.md`
- `database-seeding-tests.md`
