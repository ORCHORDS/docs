# Database Fixture Rollback Vs Truncate Strategy

Integration tests that touch a database need each test to start from a known state. Two
mechanisms dominate: *transactional rollback*, where the test runs inside a transaction that
is rolled back at the end; and *truncate*, where each test explicitly wipes the tables it
touched and re-inserts the fixture data. Each mechanism carries assumptions about isolation,
test independence, and what the database itself is allowed to do during the test. The choice
between them shapes what tests can assert, how parallel they can be, and how faithfully the
test environment matches production. Picking the wrong one produces tests that pass in
isolation but fail in CI, or tests that mask a real bug because the rollback hid the
side-effect.

## Scope

Covers the choice between transactional rollback and explicit truncate (or the equivalent
delete-and-rewrite strategy) for integration tests against relational databases — primarily
PostgreSQL, MySQL, SQLite, and the equivalent in test containers or in-memory databases. The
strategy applies whether the tests run against a real database, a containerised database, or
an in-process SQLite replica. Does not cover schema migrations, which are their own concern,
nor does it cover the question of whether integration tests against a database are warranted
at all (the test pyramid argument lives elsewhere).

## Workflow or implementation guidance

1. **Decide on isolation level first.** Test independence is the property the fixture
   strategy must preserve: a test must not see data left by another test, and a test must
   leave no data visible to another test. The two mechanisms achieve this through different
   mechanisms. Rollback depends on the database supporting nested or per-test transactions
   whose effects can be discarded; truncate depends on the test code knowing exactly what to
   remove.
2. **Prefer transactional rollback where the system-under-test allows it.** When the test
   runs inside a single transaction and the SUT uses the same connection, every write the
   SUT makes is rolled back at the end of the test. The mechanism is fast (no I/O), reliable
   (the database engine handles isolation), and self-asserting — if a test author forgets
   to seed, the empty state is obvious because the rollback leaves nothing behind.
3. **Use truncate when the SUT opens its own connection.** A common failure mode: the test
   uses connection `A` inside a transaction; the SUT uses connection `B`, committed
   independently. The rollback discards nothing visible to the SUT; subsequent tests see the
   SUT's writes. In this shape, truncate is the only honest fixture strategy. Seed data is
   inserted before the test, the test runs against committed data, and after the test the
   tables are truncated and re-seeded.
4. **Match the fixture to the assertion.** Tests that assert on row counts, on uniqueness
   constraints, or on auto-incrementing identifiers behave differently under the two
   strategies. Rollback rolls back auto-increment counters in some engines and not others;
   truncate resets counters cleanly with `TRUNCATE ... RESTART IDENTITY`. If a test asserts
   that a new row got id `42`, the fixture strategy must be deterministic about how `42` is
   reached.
5. **Prefer `TRUNCATE ... RESTART IDENTITY CASCADE` over `DELETE FROM`.** Truncate is faster
   on large tables, releases disk space back to the database, and resets sequences in one
   statement. `DELETE FROM` is row-by-row, leaves sequences running, and leaves dead tuples
   that the next test may inadvertently observe. CASCADE handles foreign-key constraints
   without the test having to manage the order.
6. **Seed deliberately, not by accident.** Truncate-and-seed strategies produce tests that
   depend on the seed data shape. The seed must be committed to the repository, versioned
   with the schema, and regenerated only when the schema changes. A seed file that drifted
   from the schema produces tests that fail in ways nobody can reproduce.
7. **Make the strategy explicit at the framework level.** Both JUnit and pytest support
   fixtures that wrap each test in a transaction (`@Transactional` in Spring, `savepoint`
   fixtures in pytest-django) or that truncate before each test. The choice lives in the
   shared fixture, not scattered across individual tests.
8. **Reserve parallel execution for truncate-based tests by default.** Two tests running in
   parallel against the same database cannot share a transaction; their isolation depends
   on truncate-and-seed. Rollback-based tests must run serially against a single database
   or each against its own dedicated connection.
9. **Audit the strategy periodically.** A test that opens a second connection, a stored
   procedure that commits inside the test, or a feature that uses connection pooling all
   break the rollback assumption. The fixture strategy is correct until something makes it
   incorrect, and that something is usually a quiet refactor.

A representative Spring Boot configuration:

```java
@TestExecutionListeners({
  TransactionalTestExecutionListener.class,
  DependencyInjectionTestExecutionListener.class
})
@Transactional
@Rollback
class OrderServiceIT { /* each test runs inside a transaction that is rolled back */ }
```

A representative truncate-based configuration for a test that opens its own connection:

```sql
BEGIN;
TRUNCATE TABLE orders, order_items, customers RESTART IDENTITY CASCADE;
INSERT INTO customers (id, email) VALUES (1, 'a@example.com');
COMMIT;
```

The truncate runs once per test, before the SUT is exercised.

## Controls

- The chosen fixture strategy is documented in the test framework's shared configuration;
  tests that violate the strategy are rejected in review.
- Truncate statements are wrapped in a single script per test schema; per-test bespoke
  cleanup is a code smell that warrants review.
- Seed data is versioned alongside the schema; a seed change without a schema change is
  flagged in CI.
- Connection pool configuration in test is bounded to a single connection for
  rollback-based strategies; multi-connection pools silently break the isolation.
- Parallel test execution is enabled only where the fixture strategy supports it.

## Validation evidence

- A test that asserts `SELECT count(*) FROM orders` after the fixture runs returns the
  expected fixture count, not zero, not the previous test's leftovers.
- A test run in parallel produces no flakes attributable to fixture state; rerunning a
  parallelised suite ten times produces identical pass/fail results.
- A deliberately broken truncate (forgetting `CASCADE` on a foreign-keyed table) is caught
  by the test environment's setup, not by a downstream test.
- A schema change updates the seed file in the same commit; the schema-without-seed case
  fails CI before merge.

## Failure modes and correction

- *Rollback chosen for a test that opens its own connection.* The test passes in isolation
  because the author sees an empty database; in CI, leftover state from earlier tests breaks
  the test in confusing ways. Convert to truncate, and add a regression test that runs the
  test alongside another writer to demonstrate the leakage.
- *Truncate chosen without `RESTART IDENTITY`.* Auto-increment counters drift between test
  runs, and tests asserting on specific ids become order-dependent. Add `RESTART IDENTITY`.
- *Seed file diverged from schema.* The fixture runs but the assertions on column shape fail
  noisily. Regenerate the seed from the schema migration; commit it in the same change.
- *Test runs `DELETE FROM` per table.* Slow on large schemas and leaves sequences running.
  Replace with a single `TRUNCATE ... CASCADE`.
- *Parallel tests share a transaction.* Race conditions surface as intermittent failures
  tied to scheduling. Disable parallelism for rollback-based strategies, or move to
  truncate.
- *Stored procedure commits inside the test.* The rollback cannot reach the procedure's
  transaction; state leaks. Either move the procedure's commit out of the test, or use a
  truncate-based strategy and reset state explicitly after the test.

## Limitations

- Transactional rollback hides side effects visible only after commit. A test that exercises
  a database trigger or a constraint that fires only at commit time may not see the
  production behaviour; pair with a small number of committed-state tests to cover that
  surface.
- Truncate is destructive; a bug in the fixture that truncates the wrong schema destroys
  data outside the test environment. The fixture script must address the test schema only,
  and the database user used by the test must have rights limited to that schema.
- Rollback-based strategies depend on the SUT participating in the test transaction. A
  refactor that opens a new connection is silent breakage; the test strategy needs periodic
  audit.
- Neither strategy covers schema-level concerns: migration correctness, index choice, and
  statistics freshness require their own dedicated tests against a real database.
- The performance advantage of rollback degrades on engines with expensive transaction
  setup. On SQLite the rollback is essentially free; on PostgreSQL with thousands of tests
  the cumulative cost matters and a hybrid strategy may win.

## Canonical sources

- ISTQB, *Certified Tester Foundation Level (CTFL) syllabus* (test isolation patterns and
  fixture strategy discussion): https://istqb.org/downloads/category/2-foundation-level-documents.html
- Testcontainers, *Testcontainers documentation* (database container lifecycle and shared
  container patterns for parallel integration suites): https://testcontainers.org/
- OWASP, *OWASP Community* resources for test data management in security-sensitive
  contexts: https://owasp.org/www-community/
