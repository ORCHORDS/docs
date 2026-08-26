# ci-test-parallelization

**Issue:** Test suites taking too long in CI due to sequential execution
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A large test suite runs serially in CI, causing pipelines that take 20+ minutes and blocking PR merges.

## Pattern / Solution
**Shard at the runner level** — split test files across multiple CI jobs:

```yaml
# GitHub Actions example
strategy:
  matrix:
    shard: [1, 2, 3, 4]
steps:
  - run: npx vitest run --shard=${{ matrix.shard }}/4
```

**Shard at the file level** — let the test framework distribute files:

```bash
# Jest
jest --maxWorkers=50%

# Playwright
playwright test --shard=1/4
```

For database-backed tests, spin up one isolated DB per shard (use random port or schema prefix). Merge coverage reports after all shards complete using the framework's merge command.

## Gotchas
- Shared stateful resources (a single DB, a single Redis) across shards cause race conditions.
- Uneven file sizes cause some shards to finish much earlier than others — consider `--shard` with `--reporter=list` output to balance manually.
- Cache node_modules and build artifacts between shards to avoid redundant installs.

## Related
- playwright-parallel-execution
- test-environment-management
- flaky-test-detection
