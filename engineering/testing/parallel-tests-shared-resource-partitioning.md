# parallel-tests-shared-resource-partitioning

**Issue:** The suite was parallelized at the CI level (`ci-test-parallelization.md`) and per-test isolation exists (`test-database-isolation.md`), but stateful integration tests still collide when run at the same time: worker B truncates the table worker A is counting, two workers run migrations against one database, Redis keys bleed across suites, and the flakes get weirder the more workers are added. This article covers the missing middle layer: partitioning SHARED resources (databases, caches, queues, ports) per worker so parallel stateful tests are both fast and correct. Based on 2025 practice with pytest-xdist worker-ID patterns, Postgres template databases, and Testcontainers-per-worker.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why parallelism breaks on shared state

1. **Per-test isolation does not survive concurrency.** Transaction-rollback-per-test assumes one test running at a time; with four workers on one database, worker A's uncommitted transaction and worker B's `count()` interleave, and assertions about "1 row" find 4. Mergify's 2025 write-up on pytest-xdist calls this exactly right: "the suite gets faster and the flakes weirder."
2. **Setup races: migrations and seeding.** Two workers booting the app both run `migrate.latest()` against the same DB — duplicate-column errors, lock waits, or half-migrated state that poisons every subsequent test in both workers.
3. **Name collisions on fixed identifiers.** Tests using fixed names (user `test-1`, tenant `acme`, topic `orders`) work serially and collide the moment two workers create them concurrently — the error appears far from the cause because it depends on scheduler ordering.
4. **Port and socket exhaustion.** Fixed listener ports (`3001`, `5433`) collide between workers; conversely, unbounded container-per-test creation exhausts CI memory, disk, or the Docker daemon's process limits.
5. **Connection-pool math changes under parallelism.** 4 workers × pool of 20 connections = 80 connections against a Postgres default `max_connections=100`; the suite intermittently fails at peak with "too many clients" and everyone blames the network.

## Database partitioning strategies (strongest to weakest)

1. **Database-per-worker via template cloning — the strongest pattern.** Migrate + seed ONCE into a template database, then each worker executes `CREATE DATABASE test_gw0 TEMPLATE test_template` (Postgres) in a worker-ID-aware fixture and drops it at exit. Cloning is seconds-fast, workers share nothing, and migrations never race. This is the standard 2025 pytest-xdist recipe and translates directly to Jest/Vitest `workerId`.
2. **Schema-per-worker when you cannot create databases.** Cloud-managed Postgres often restricts `CREATE DATABASE`; instead create `test_gw0..gwN` schemas from a template schema and set each worker's `search_path` (or use the worker ID in table prefixes). Same isolation, slightly more migration plumbing since migrations must run per schema.
3. **Container-per-worker (Testcontainers).** Give each worker its own ephemeral Postgres/Redis container on a random port — total isolation including engine-level state, at the cost of boot time and CI memory; the leen.dev 2025 pipeline rewrite credits this pattern for eliminating their cross-worker flakes. Best for medium worker counts (≤8) on CI runners with RAM headroom.
4. **Single database + table-prefix-per-worker.** Weakest useful option: every table name (or critical fixture row key) gets a worker-ID suffix. No engine features needed, but every query path must respect the prefix — one raw SQL string without it reintroduces the race silently. Use only when neither databases nor schemas are creatable.
5. **Keep per-test hygiene INSIDE the partition.** Partitioning removes cross-worker interference, not cross-test interference; each worker still needs truncation/rollback between its own tests, or you have merely moved the flake from "random other worker" to "previous test in this worker."

## Namespacing non-database resources

1. **Redis/cache: key-prefix per worker.** Wrap the client in a fixture that prefixes every key with `${workerId}:` (or select a dedicated logical DB index per worker); a missed `FLUSHDB` in one worker then cannot evict another's session state. Never call `FLUSHALL` in a parallel suite.
2. **Queues/topics: consume only your partition.** Give each worker its own queue name or consumer group (e.g. `orders.gw2`) and have the producer route to the active worker's queue; a shared consumer group balances messages to random workers, which looks exactly like lost messages in tests.
3. **Ports: never hardcode.** Bind test servers to port 0 (OS-assigned) or allocate from a per-worker range (`4000 + workerId * 100`); a fixed port works in serial CI and fails only when the second worker starts — usually on Fridays.
4. **Filesystem and temp paths: worker-suffixed.** Shared tmp dirs, snapshot folders, and uploaded-file roots collide identically to databases; derive all paths from `os.tmpdir() + workerId` and clean up per worker, not globally.
5. **External SaaS sandboxes: account-per-worker.** Stripe/test-payment or email sandbox state is shared by nature; create one test account per worker at suite start (API-driven) so one worker's cleanup never deletes another's fixtures mid-flight.

## Worker-aware fixtures and orchestration

1. **Propagate the worker ID everywhere.** pytest-xdist exposes `worker_id` (`gw0`, `gw1`, master = `master`); Jest/Vitest expose `process.env.JEST_WORKER_ID` / `process.env.VITEST_POOL_ID`. Read it in ONE fixture and derive every partitioned name (DB, schema, prefix, ports, dirs) from it — ad-hoc reads scattered through the suite guarantee someone uses the wrong one.
2. **Run setup once, on the controller, before workers fork.** Build the template database/seed set in a single-controller hook, then let workers clone it; per-worker migration from scratch multiplies the slowest part of the suite by the worker count.
3. **Group correlated tests into one worker's scope.** xdist's `loadscope`/`loadfile` (and Jest's default per-file isolation) keep same-module tests on one worker, so module-level fixtures and ordering assumptions survive parallelism without full partitioning.
4. **Tear down per partition, idempotently.** Workers die on failure; cleanup must not assume graceful shutdown. Drop `test_gw*` databases/prefixed keys from a controller-level teardown that pattern-matches worker partitions regardless of which workers finished.
5. **Make collisions loud.** Wrap shared-resource creation so a duplicate name (DB exists, port in use, account taken) fails immediately with "created by worker X at Y" instead of passing weirdly by reusing the other worker's state — silent reuse is the worst failure mode because tests pass for the wrong reason.

## When NOT to parallelize (or to partition less)

1. **Ordering/timing-sensitive suites (migrations, scheduler/cron, backfill logic) often cost less serialized.** If partitioning requires mocking the very behavior under test, a serial tagged subset (`-m serial`, Playwright `test.describe.serial`) is the honest design, not a heroic partition.
2. **Single-writer resources (a legacy DB with no CREATE rights, one shared sandbox) cap the ceiling.** Partition what you can and serialize only the tests that truly need the singleton; all-or-nothing thinking leads to serializing everything.
3. **If a suite runs in <2 minutes, partitioning is probably premature** — worker boot, container startup, and template cloning can eat the savings. Revisit when runtime actually hurts, with measurements.
4. **Flaky tests plus parallelism multiply debugging cost.** Stabilize or quarantine known flakes (see `flaky-test-remediation.md`) BEFORE adding workers, or you cannot tell new concurrency bugs from old flakiness.
5. **Budget CI resources before scaling workers.** 8 workers × per-worker Postgres container needs a bigger runner than the default; measure peak memory of one full-parallel run and provision for it, or trade container-per-worker down to template-database-per-worker (much lighter) on constrained runners.

## Related

- `ci-test-parallelization.md` — CI-level sharding (the outer layer)
- `test-database-isolation.md` — per-test isolation (the inner layer this article builds between)
- `test-containers-docker.md` — ephemeral container mechanics
- `shared-test-state-antipatterns.md` — code-level shared-state bugs
- `flaky-test-detection.md` — diagnosing the flakes parallelism exposes
