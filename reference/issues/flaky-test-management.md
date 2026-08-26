# flaky-test-management

## Symptom

A test passes locally, passes on the developer's branch, but fails
intermittently on CI — or vice versa. Re-running the same commit with no code
changes produces a different result. Over time, the team loses trust in the test
suite: engineers start re-running builds until they go green ("retry until
pass"), ignore failures ("oh that's just the flaky one"), or disable tests
outright. Eventually a real regression slips through because everyone assumed the
red build was "just flakiness."

Flaky tests are a silent tax. Each one costs 5-30 minutes of engineer time per
occurrence (context switch, investigation, retry). A suite with 20 flaky tests
in a CI pipeline that runs 50 times per day can consume hundreds of engineer-
hours per quarter and erode confidence in the entire test signal.

## Common Root Causes

- **Test order dependence.** Test A mutates global/shared state (DB rows, env
  vars, filesystem, module cache) and Test B relies on the original state.
  Passing alone but failing in a suite, or vice versa.
- **Timing / race conditions.** `setTimeout(..., 100)` that's enough on a fast
  dev machine but races on a loaded CI runner. Awaiting an event that fires
  before the listener attaches. Polling loops with fixed sleeps.
- **Hidden async gaps.** A test fires a side effect (DB write, network call)
  without awaiting completion, then asserts. Sometimes the assertion runs before
  the effect lands.
- **Time and date coupling.** Tests that depend on "now." Run at 23:59 local,
  they cross midnight and fail. Run in a different timezone, they fail. DST
  transitions break them twice a year.
- **Random data in fixtures.** Tests using `Math.random()`, UUIDs, or generated
  data that occasionally collide or hit edge cases.
- **Shared external resources.** Tests that hit a real DB, real API, real
  filesystem path without isolation. Two CI shards running the same test
  collide. A previous test left dirty data.
- **Floating point and locale.** String formatting of numbers/dates that varies
  by locale setting on the runner.
- **Resource exhaustion.** Tests that spawn processes, open handles, or create
  connections without cleanup. After N tests, the runner runs out of file
  descriptors, memory, or ports.

## Gotchas

- **"Cannot reproduce locally" is the #1 trap.** CI runners are slower, more
  loaded, run in a different timezone, and execute tests in a different order
  than your dev machine. Reproduce by mimicking those conditions — not by
  re-running on your laptop and concluding "it's fine."
- **Quarantine is a band-aid, not a fix.** Moving a flaky test to a
  `@quarantine` folder or `test.skip` stops the noise but the underlying bug
  remains. Set a hard SLA: quarantined tests must be fixed or deleted within N
  days, not left forever.
- **Retrying flaky tests hides regressions.** Configuring CI to "retry failed
  tests up to 3 times" converts a 90% reliable test into a 99.9% reliable one —
  but it also hides the 10% of the time a *real* regression fails the same way.
  Retries should be a last resort with explicit tracking, not a default.
- **Order-dependence is invisible until you shuffle.** Most test runners run in
  file/declaration order by default. Run with `--randomize` or `--shuffle` and
  suddenly 8 tests start failing — those have always been flaky, you just never
  knew.
- **Mocks leak across tests.** `vi.mock()` / `jest.mock()` at module scope
  affects all tests in the file. A test that relies on the mock passes when run
  after the mocking test, fails when run alone. Prefer per-test mocks or
  explicit `beforeEach`/`afterEach` restoration.
- **Snapshot tests are flaky time bombs.** A snapshot that was captured against
  unstable output (Date, random, sorted-but-unstable-order) will fail
  nondeterministically. Never snapshot anything with nondeterministic content.
- **Tests that pass when watched but fail in CI.** Watch mode often runs with
  different flags, caching, or module resolution than the CI invocation. Always
  validate against the exact CI command: `pnpm test --run`, not the watch
  default.

## Detection and Triage Workflow

1. **Instrument flake rate.** Tag every CI test run with pass/fail and track per-
   test reliability over time. Tools: `flaky-tests` GitHub Action, BuildPulse,
   or a simple script parsing JUnit XML. A test that fails >1% of the time on
   the same commit is flaky.
2. **Capture artifacts on failure.** Save logs, screenshots, DB dumps, and the
   exact seed/order for every failure. Without artifacts you cannot reproduce.
3. **Reproduce with the "RNER" method**: Run N times, Empty cache, Randomize
   order, Emulate CI env. `for i in {1..50}; do pnpm test --run; done` catches
   most intermittent failures.
4. **Bisect to the test pair.** If only failing in a suite, use
   `--testNamePattern` + `--testPathPattern` to find the minimal failing set.
   Usually it's one test mutating state that another depends on.
5. **Fix or delete.** Never leave a known-flaky test in the suite. Either fix
   the root cause, rewrite the test to be deterministic, or delete it (a deleted
   test is better than a test that lies).

## Prevention

- **Enforce test isolation by default.** Each test sets up and tears down its own
  state. Use `beforeEach`/`afterEach`, in-memory DBs with per-test transactions,
  temp directories (`tmp-promise`, `os.tmpdir()`), and explicit cleanup.
- **Inject time, don't read it.** Pass a `Clock` abstraction into code under
  test. Use `vi.useFakeTimers()` / `jest.useFakeTimers()` and
  `vi.setSystemTime()`. Never let `new Date()` or `Date.now()` reach production
  code unparameterized.
- **Inject randomness.** Seed `Math.random` (`vi.spyOn(Math, 'random')`) or use
  a seeded PRNG. For UUIDs in tests, use deterministic test factories.
- **Contract tests, not integration tests, for external services.** Don't hit a
  real DB or HTTP API in unit tests. Use `msw` for HTTP, `pg-mem` or testcontainers
  with per-test rollback for DBs.
- **Run CI with `--shuffle` on one job.** Keep a deterministic-order job for
  stable signal, but add a parallel shuffled job to surface order-dependence
  early.
- **Fail-fast on new flakes.** When a previously-green test flakes, fail the
  build and require investigation — don't auto-retry silently.
