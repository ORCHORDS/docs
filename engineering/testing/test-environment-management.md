# test-environment-management

**Issue:** Keeping test environments consistent, isolated, and reproducible across local and CI runs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests pass locally but fail on CI because of missing env vars, different database versions, or shared mutable state between runs.

## Pattern / Solution
Codify environment configuration in checked-in files:

- `.env.test` for non-secret defaults committed to the repo.
- CI secrets injected via the pipeline's secret store, never hard-coded.
- `docker-compose.test.yml` for external services (Postgres, Redis, etc.) so any machine can spin them up identically.

Use a setup script that validates required env vars before the suite starts:

```ts
// globalSetup.ts
const required = ["DATABASE_URL", "REDIS_URL"];
for (const key of required) {
  if (!process.env[key]) throw new Error(`Missing env var: ${key}`);
}
```

Tear down containers after the suite completes in CI to avoid resource leaks.

## Gotchas
- Never read production env vars in test runs — use a separate `.env.test` override.
- Database URL in `.env.test` should point to a dedicated test database, not the dev DB.
- Ensure timezone (`TZ=UTC`) is set identically locally and in CI to avoid date-related flakiness.

## Related
- test-containers-docker
- test-database-isolation
- ci-test-parallelization
