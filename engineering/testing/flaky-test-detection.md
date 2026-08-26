# flaky-test-detection

**Issue:** Identifying which tests are intermittently failing across CI runs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Some tests fail on CI once every few runs for no obvious reason, eroding team trust in the suite and wasting investigation time.

## Pattern / Solution
**Aggregate CI results** — use a test results database (Buildkite analytics, Datadog CI, or a simple SQLite table) to store pass/fail per test per run. Query for tests with a failure rate between 1% and 50% — those are flaky candidates.

**Reproduce locally with repeat runs:**

```bash
# Jest
jest --testNamePattern="my flaky test" --runInBand --testRetries=0
# run it 50 times
for i in $(seq 50); do jest --testNamePattern="..." || echo "FAILED on $i"; done
```

**Playwright built-in detection:**

```bash
playwright test --repeat-each=10
```

Label detected flaky tests with a `[flaky]` tag or skip annotation and file a tracking issue immediately. Flaky tests should be quarantined (not deleted) while being fixed.

## Gotchas
- A test that always fails is not flaky — it is broken. Flakiness implies non-determinism.
- Network calls, timers, and random seeds are the top three flakiness sources.
- Do not re-run-on-failure as a permanent fix; it hides root causes and inflates CI time.

## Related
- flaky-test-remediation
- test-retry-strategies
- ci-test-parallelization
