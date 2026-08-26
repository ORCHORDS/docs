# database-test-fixtures-isolation

**Issue:** Integration tests that run against a real database are the only tests that catch real SQL bugs — wrong joins, missing migrations, constraint violations, ORM misconfigurations — but they are slow and stateful. If each test sees rows left behind by earlier tests, the suite becomes order-dependent, fails randomly in CI, and eventually gets skipped or deleted. The engineering problem is choosing an isolation strategy (transaction rollback, truncation, fresh database, copy-on-test) and a fixture strategy (factories versus static dumps) that keeps the suite fast enough to run on every commit while guaranteeing every test starts from a known state.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Isolation strategies compared

1. **Transaction rollback per test.** Wrap each test in an explicit transaction (`BEGIN` before, `ROLLBACK` after) so nothing it writes survives. It is by far the fastest option — published case studies show suites dropping from minutes to seconds (an 86x speedup in one Ruby migration) because no cleanup I/O happens at all, and it enables safe parallelism within one database.
2. **Truncation between tests.** `TRUNCATE ... RESTART IDENTITY CASCADE` on all tables after each test (the Rails/Django default). Slower — every test pays a cleanup cost — but robust because it works even when the code under test commits real transactions.
3. **Fresh database per class or per run.** Create the schema from migrations, run a batch of tests, drop the database. Cheapest realistic variant is a template database: build `test_template` once, then `CREATE DATABASE test_x TEMPLATE test_template` per worker, which is a fast file-level copy.
4. **Copy-on-test for file-based databases.** With SQLite the entire database is one file; copying a pre-seeded file per test (or per worker) gives perfect isolation with zero cleanup logic. Do not do this for Postgres and then claim the tests prove anything about Postgres.
5. **Never rely on test ordering.** Whatever strategy is picked, order-independence is the acceptance criterion: a suite that only passes in registration order has hidden state leaks and will break the day CI shuffles tests.

## Where transaction rollback silently fails

1. **Code under test opens its own transaction.** Rollback isolation only works if every write happens inside the test's transaction. Spring's `@Transactional` tests are the classic trap: a service method annotated `REQUIRES_NEW`, or any code that commits on a separate connection, writes data the rollback never touches, contaminating later tests.
2. **Async and background execution.** Workers, schedulers, and fire-and-forget pools grab their own connections from the pool, so their writes commit outside the rolled-back transaction. Either join the test transaction (inject the connection) or switch those tests to truncation/fresh-database mode.
3. **Tests of behavior that only happens at commit.** Deferred constraints, `ON COMMIT DROP` temp tables, `LISTEN/NOTIFY` delivery, and two-phase commit cannot be tested inside a never-committed transaction; the rollback strategy must have an escape hatch for these cases.
4. **Transaction-mode poolers.** If the test harness connects through PgBouncer in transaction mode, session state and savepoint tricks misbehave; point tests directly at Postgres.
5. **Detection is a shuffled CI run.** Run the suite in random order in CI (Vitest `sequence.shuffle`, Jest `--randomize`, pytest-random-order). Cross-test contamination shows up immediately as flaky failures that point at the leaking test.

## Fixture design

1. **Factories over static dumps.** A factory/builder per table (create a valid row, override only what the test cares about) beats a giant `fixtures.yml`: each test declares its dependencies, unknown-column breakage is localized, and there is no shared god-fixture whose meaning erodes. Keep total dependence count visible by making factories compose (`createUser()` then `createPost({ authorId })`).
2. **Seed once, restore to checkpoint.** With rollback isolation, seed reference data (lookups, enum-ish tables) once in `beforeAll` inside the wrapping transaction so every test in the file sees it and the final rollback removes it. With truncation, keep a `seedReferenceData()` that truncation-callbacks re-run cheaply.
3. **Minimal per-test data.** Each test creates only the rows it needs. Tests that depend on "whatever the last test left" are the ones deleted in frustration six months later.
4. **Deterministic values.** Fixed UUIDs and timestamps from factories, not `now()` or random values computed inside assertions; clock-dependent assertions are the top source of flaky DB tests.
5. **Respect constraints in fixture order.** Factories should insert parents before children or use deferrable FKs; a fixture layer that fights constraint ordering produces tests that pass only by luck of insertion sequence.

## Testcontainers and environment hygiene

1. **Ephemeral containers per suite.** Use Testcontainers (or a docker-compose spun up by the test runner) so every CI run starts from a pristine Postgres. Reuse one container across the whole suite run for speed — the isolation strategy, not the container, keeps tests independent.
2. **Pin the production major version.** Tests against Postgres 16 while production runs 17 catch nothing about 17 behavior; the container tag should come from one config source shared with infra.
3. **Run real migrations at bootstrap.** Apply the actual migration chain (not an ORM auto-sync) before tests. This turns every test run into a migration smoke test and catches drift between entities and schema for free.
4. **No shared dev database.** A shared dev Postgres mutated by tests and humans simultaneously is unfixable; every developer and CI job gets its own instance or database.

## CI parallelism

1. **Database-per-worker.** When distributing tests across CI shards, give each worker its own database (from the template-database trick) or its own schema; two workers truncating the same tables corrupt each other's runs.
2. **Budget the suite.** Decide the wall-clock budget for DB tests (e.g. under 2 minutes locally) and measure; a slow suite gets skipped, which is worse than no suite because it looks like coverage.
3. **Fail on order dependence.** Keep the randomized-order mode on in CI permanently. Flakiness from state leaks should be a red build the day it appears, not an urban legend.
