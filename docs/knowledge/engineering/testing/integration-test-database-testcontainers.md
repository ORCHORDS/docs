# Integration Test Database Testcontainers

Integration tests that touch a database need a database. The choice between an in-memory
SQLite, a mocked database, and a real database instance is the difference between testing
the SQL the SUT emits and testing the SQL the database actually accepts. Testcontainers
provides the third option: a real database engine running inside a container, spun up per
test run, torn down at the end. The SUT talks to it through a normal connection string; the
test environment owns its lifecycle. The trade-off is real-engine fidelity at the cost of
container orchestration overhead, but for tests that exercise migrations, indexes,
constraints, or engine-specific behaviour, no in-memory substitute is faithful enough.

## Scope

Covers the use of Testcontainers for integration tests against relational databases,
key-value stores, message brokers, and other dependency services in Java, Node, Python,
Go, and .NET. Applies to tests that run locally, in CI, and in pre-deployment environments.
Does not cover the production deployment of the same containers, nor the choice of which
database engine to use (Testcontainers works with any engine that has a Docker image).

## Workflow or implementation guidance

1. **Choose the engine image deliberately.** Testcontainers runs the engine as a Docker
   image. The image should match the production engine version and configuration closely
   enough that engine-specific behaviour is meaningful: the right major version, the right
   collation, the right extensions. A test against PostgreSQL 14 with `pg_trgm` disabled
   cannot validate a query that depends on trigram indexes.
2. **Decide on container lifecycle: per-class, per-suite, or per-run.** Three patterns
   dominate:
   - **per-class** (or per-test in JUnit / pytest): each test starts a fresh container.
     Strongest isolation, highest startup cost.
   - **per-suite** (or per-module): the container starts once for the suite, tests run
     sequentially against it. Faster startup, weaker isolation; tests must reset state
     between cases.
   - **per-run** (or shared singleton): the container starts once for the whole CI run;
     tests run in parallel against it via different schemas or databases. Fastest startup,
     weakest isolation; requires careful state management.
   The choice depends on test duration budget, parallelisation strategy, and how much state
   each test creates.
3. **Use a reusable container for shared use.** Testcontainers supports reusable containers
   that survive between test classes when the same engine and version are needed. Reusable
   containers cut startup cost but require explicit teardown logic; a test that fails to
   clean up state on a reusable container leaves it dirty for the next suite.
4. **Initialise via init scripts.** Container construction accepts SQL init scripts that run
   on first boot: schema migrations, seed data, extensions. The init scripts are the
   canonical test schema; they should match the migrations the production database would
   apply, not a parallel test-only schema. Diverging schemas produces tests that pass against
   the test schema and fail against production.
5. **Wait for readiness, not for port-up.** A container whose port is open is not
   necessarily ready to accept queries. Use Testcontainers' wait strategies
   (`waitForLogMessage`, `waitForDatabaseQuery`) that confirm the engine is responsive. A
   test that races the engine's startup produces flakes that look like the engine's fault
   but are the test framework's fault.
6. **Wire the connection string through the SUT's configuration.** The SUT's database URL
   must be overridable via environment variable or configuration file. The test sets the
   URL to point at the container's port before exercising the SUT. A test that requires
   code changes to point at the container is a test that cannot run in CI.
7. **Manage parallel access via schemas or databases, not via ports.** Multiple test
   processes against the same container run against different schemas or different
   databases, not against different ports. A test that binds to a hard-coded port cannot
   run in parallel with another test that binds to the same port.
8. **Capture diagnostic data on failure.** A failed integration test against a real
   database should produce the SUT's logs, the database's logs (via the container's log
   stream), and a query log if the engine supports it. Without these, a failure inside the
   database engine is invisible to the test report.
9. **Tear down deterministically.** A `Ryuk` container (Testcontainers' reaper) cleans up
   containers left behind by aborted test runs. Verify it runs in CI; without it, a flaky
   pipeline leaves containers running that exhaust Docker's resources and break the next
   pipeline.

A representative Testcontainers setup for PostgreSQL in a Node test:

```ts
import { PostgreSqlContainer } from '@testcontainers/postgresql';

const container = await new PostgreSqlContainer('postgres:16')
  .withDatabase('test')
  .withUsername('test')
  .withPassword('test')
  .withInitScript('./fixtures/init.sql')
  .start();

process.env.DATABASE_URL = container.getConnectionUri();
```

The SUT then reads `DATABASE_URL` exactly as it does in production, the only difference
being the value.

## Controls

- Container images are pinned to specific versions; a floating tag (`postgres:latest`) is
  not allowed.
- Wait strategies are configured for every container; a container started without a wait
  strategy is treated as a flake source.
- The connection URL is injected via configuration, not hard-coded.
- The test framework runs `Ryuk` (or equivalent cleanup) in CI; orphan containers are
  detected by a periodic check.
- Diagnostic data (engine logs, query logs) is captured on failure and retained for the
  agreed retention window.

## Validation evidence

- A query that uses engine-specific syntax (for example, PostgreSQL's `ON CONFLICT`) is
  exercised against the real engine and passes; against an in-memory substitute that does
  not support the syntax, the test would fail.
- A migration that adds an index is observed to speed up the relevant query against the
  container; the test asserts both correctness and performance impact.
- A test that depends on constraint enforcement (foreign keys, unique constraints,
  check constraints) is observed to fail when the SUT violates the constraint; against a
  mocked database, the constraint would never fire.
- Parallel test runs against the same container complete without flakes attributable to
  shared state.

## Failure modes and correction

- *Container not ready when the test runs.* Add a wait strategy; do not add arbitrary
  sleep delays.
- *Container version drift between local and CI.* Pin the image tag; the same tag must
  resolve to the same engine configuration everywhere.
- *Connection URL hard-coded.* Refactor the SUT's configuration to read from environment;
  tests set the environment.
- *Init script diverged from production migrations.* Regenerate the init script from the
  migrations; commit them together.
- *Containers orphaned after a crashed pipeline.* Verify `Ryuk` is running in the CI
  environment; add a periodic orphan-check script.
- *Test parallelisation breaks isolation.* Move to schema-per-test or database-per-test;
  do not share a schema across parallel tests.
- *Engine-specific syntax assumed but engine version doesn't support it.* Pin the engine
  version explicitly; assert the syntax is available before relying on it.

## Limitations

- Container startup is non-trivial — typically several seconds per container. For test
  suites with thousands of cases, per-test startup dominates the budget; per-suite or
  per-run reuse becomes necessary, with the isolation trade-off that comes with it.
- Testcontainers requires Docker. In environments without Docker (some CI runners,
  restricted build agents), the strategy is unavailable; substitute with a local engine
  install or an in-memory alternative and accept the fidelity gap.
- A real engine behaves like a real engine in most ways; in a few, it differs. Memory
  pressure, disk-full errors, replication lag, and engine-internal caching are not faithful
  to production even with Testcontainers; they require their own dedicated tests.
- Network latency between the SUT and the container is a hop on the local Docker network,
  not the production network. Performance tests against a Testcontainers database measure
  the engine, not the network.
- Container images must be available to the test environment. Air-gapped CI requires a
  mirror; a missing image is a pipeline-killer that no Testcontainers configuration can
  recover from.

## Canonical sources

- AtomicJar, *Testcontainers documentation* (container lifecycle, wait strategies, module
  index by language): https://testcontainers.org/
- Shopify, *Toxiproxy* (complementary tool for fault injection against Testcontainers
  dependencies): https://github.com/Shopify/toxiproxy
- Cloudflare, *Testing on Cloudflare Workers* (Miniflare and Vitest integration patterns
  for tests that use Testcontainers-style isolated environments):
  https://developers.cloudflare.com/workers/testing/
