# test-coverage-meaningful-metrics

**Issue:** Using code coverage numbers meaningfully rather than gaming the percentage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams chase 80%+ coverage thresholds by writing trivial tests, while genuinely risky code paths remain untested.

## Pattern / Solution
Treat coverage as a smell detector, not a quality score:

1. **Look at uncovered lines**, not the percentage — a red line in a payment handler matters more than 100% coverage on a utility formatter.
2. **Use branch coverage**, not just line coverage — line coverage misses untaken `else` branches.
3. **Track coverage trends** in CI: fail the build only when coverage *decreases* on changed files, not when global coverage is below a threshold.
4. **Exclude generated files and config** from coverage reports (migrations, protobuf output, `*.config.ts`).

```ts
// vitest.config.ts
coverage: {
  provider: "v8",
  exclude: ["**/*.config.ts", "**/migrations/**", "**/__generated__/**"],
  thresholds: { perFile: true, branches: 70, lines: 80 },
}
```

## Gotchas
- 100% coverage does not mean 100% correctness — tests can cover code without asserting anything meaningful.
- Mutation testing (see mutation-testing-stryker) reveals gaps that coverage misses.
- Integration and E2E tests also contribute to coverage — collect combined reports with `--merge-coverage`.

## Related
- jest-coverage-thresholds
- vitest-coverage-v8
- mutation-testing-stryker
