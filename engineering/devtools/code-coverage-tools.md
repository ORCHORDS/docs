# Code Coverage Tools

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your test suite passes but you have no visibility into which lines, branches,
or functions are actually exercised by tests. You cannot answer "what
percentage of the codebase is tested?" or "which critical paths have zero
test coverage?" PRs merge without coverage gates, and regressions appear in
untested code paths.

## Context

Code coverage measures how much of your source code is executed during test
runs. Coverage tools instrument the code (source or bytecode), run the tests,
and produce a report showing covered vs. uncovered lines, branches,
functions, and statements. Coverage is a necessary but not sufficient quality
signal — high coverage does not guarantee correctness, but low coverage
guarantees blind spots.

## Tool landscape (2026)

### JavaScript/TypeScript

| Tool | Mechanism | Speed | Best for |
|---|---|---|---|
| **c8** | V8 native coverage (NODE_V8_COVERAGE) | Fastest | Node.js projects; no transform overhead |
| **Istanbul/nyc** | Source instrumentation (Babel plugin) | Medium | Legacy projects, broad ecosystem |
| **Vitest coverage (v8)** | Built-in c8/Istanbul integration | Fast | Vitest projects — `vitest --coverage` |
| **Jest --coverage** | Istanbul (Babel) or v8 | Medium | Jest projects — `jest --coverage` |

### Other ecosystems

| Language | Tool | Notes |
|---|---|---|
| Go | `go test -cover` | Built-in; `-coverprofile` for CI integration |
| Python | `coverage.py` + `pytest-cov` | Branch coverage with `--branch` flag |
| Java | JaCoCo | Bytecode instrumentation; Gradle/Maven plugins |
| Rust | `cargo-tarpaulin` or `llvm-cov` | `llvm-cov` preferred for accuracy in 2026 |
| .NET | Coverlet | Cross-platform; integrates with `dotnet test` |

### Coverage reporting services

| Service | Features |
|---|---|
| **Codecov** | PR comments, coverage diff, flag-based merging, YAML config |
| **Coveralls** | PR status checks, badge generation, history tracking |
| **SonarQube** | Coverage + code quality + security in one platform |

## Setting coverage thresholds

```json
// vitest.config.ts — coverage configuration
{
  "test": {
    "coverage": {
      "provider": "v8",
      "reporter": ["text", "lcov", "json-summary"],
      "thresholds": {
        "statements": 80,
        "branches": 75,
        "functions": 80,
        "lines": 80
      },
      "exclude": [
        "**/*.test.ts",
        "**/*.spec.ts",
        "**/test/**",
        "**/mocks/**"
      ]
    }
  }
}
```

```yaml
# GitHub Actions: upload coverage to Codecov
- name: Upload coverage
  uses: codecov/codecov-action@v4
  with:
    files: coverage/lcov.info
    fail_ci_if_error: true
```

## Meaningful coverage metrics

- **Line coverage** — percentage of executable lines hit. Most common metric.
- **Branch coverage** — percentage of conditional branches (if/else, ternary,
  switch) taken. More meaningful than line coverage for logic-heavy code.
- **Function coverage** — percentage of functions called. Quick sanity check.
- **Modified coverage** — coverage of lines changed in the current PR. More
  actionable than total coverage for code review.

## Anti-patterns

- **Chasing 100% coverage** — diminishing returns above 80-85%. The last 15%
  typically covers error handlers, platform-specific branches, and
  generated code that are expensive to test and low-risk.
- **Coverage without assertions** — executing code without asserting
  behavior produces high coverage with no quality signal. Coverage measures
  execution, not correctness.
- **Global threshold only** — a global 80% threshold lets critical modules
  (auth, payments) hide at 40% coverage while utility modules inflate the
  average. Set per-module thresholds for critical paths.
- **Excluding too much** — excluding test helpers is fine. Excluding entire
  directories to hit the threshold is gaming the metric.

## Gotchas

- **V8 coverage vs. Istanbul** — V8 native coverage (c8) is faster but may
  report slightly different numbers than Istanbul due to different
  instrumentation approaches. Pick one and stick with it.
- **Source maps** — TypeScript/JSX projects need correct source maps for
  accurate coverage. Misconfigured source maps produce coverage reports
  against transpiled code, not source code.
- **Parallel test execution** — running tests in parallel requires merging
  coverage reports. Use `lcov` format and merge with `lcov-result-merger`
  or your CI service's coverage merging feature.
- **Flaky coverage** — conditional imports, feature flags, and environment-
  dependent branches cause coverage numbers to fluctuate between runs.
  Pin the test environment.

## Verification

- Coverage report generates on every PR and is visible in the PR review.
- Coverage thresholds are enforced in CI — PRs that drop coverage below
  the threshold cannot merge.
- Critical modules (auth, payments, data access) have per-module coverage
  thresholds set higher than the global minimum.

## Related

- `documentation/categories/testing/test-coverage-meaningful-metrics.md`
- `documentation/categories/testing/test-pyramid-strategy.md`
- `documentation/categories/testing/vitest-coverage-v8.md`
- `documentation/categories/testing/jest-coverage-thresholds.md`

## Source URLs (verified 2026-08-16)

- c8 — https://github.com/bcoe/c8
- Istanbul/nyc — https://istanbul.js.org/
- Codecov documentation — https://docs.codecov.com/
- Vitest coverage — https://vitest.dev/guide/coverage
