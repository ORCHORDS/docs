# test-containers-docker

**Issue:** Spinning up real databases and services in Docker for integration tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Integration tests need a real PostgreSQL, Redis, or Kafka instance. Testcontainers manages Docker containers programmatically.

## Pattern / Solution
```bash
npm install -D testcontainers
```

```ts
import { PostgreSqlContainer } from "@testcontainers/postgresql";
import { RedisContainer } from "@testcontainers/redis";

let pgContainer: StartedPostgreSqlContainer;
let redisContainer: StartedRedisContainer;

beforeAll(async () => {
  [pgContainer, redisContainer] = await Promise.all([
    new PostgreSqlContainer("postgres:16-alpine").start(),
    new RedisContainer("redis:7-alpine").start(),
  ]);

  process.env.DATABASE_URL = pgContainer.getConnectionUri();
  process.env.REDIS_URL = `redis://${redisContainer.getHost()}:${redisContainer.getMappedPort(6379)}`;

  await runMigrations(process.env.DATABASE_URL);
}, 60_000); // 60s timeout for Docker pull

afterAll(async () => {
  await pgContainer.stop();
  await redisContainer.stop();
});
```

## Gotchas
- Docker must be running — not available in all CI environments (use GitHub Actions services instead)
- Start containers in `globalSetup` when sharing across test files
- Use `alpine` images for faster startup
- First run is slow (image pull) — CI layers cache images

## Related
- `integration-test-database.md`
- `d1-testing-local.md`
- `kv-testing-miniflare.md`
