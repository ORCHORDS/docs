# integration-test-database

**Issue:** Testing database interactions in integration tests without mocking the DB
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mocking database calls in unit tests misses SQL errors, constraint violations, and ORM bugs. Integration tests hit a real DB.

## Pattern / Solution
Using PostgreSQL with test containers:
```ts
// jest.config.ts — set longer timeout for DB tests
testTimeout: 30000,
globalSetup: "./src/test/globalSetup.ts",
globalTeardown: "./src/test/globalTeardown.ts",

// globalSetup.ts
import { GenericContainer } from "testcontainers";

export default async () => {
  const container = await new GenericContainer("postgres:16")
    .withEnvironment({ POSTGRES_PASSWORD: "test", POSTGRES_DB: "testdb" })
    .withExposedPorts(5432)
    .start();

  process.env.DATABASE_URL = `postgresql://postgres:test@localhost:${container.getMappedPort(5432)}/testdb`;
  (global as any).__pg_container__ = container;
};
```

Run migrations before tests:
```ts
beforeAll(async () => {
  await runMigrations(process.env.DATABASE_URL);
});
```

## Gotchas
- Each test file should use transactions rolled back in afterEach
- Testcontainers startup adds 5-15s — run once in globalSetup
- Use a separate test database, never production

## Related
- `test-containers-docker.md`
- `transactional-test-rollback.md`
- `test-database-isolation.md`
