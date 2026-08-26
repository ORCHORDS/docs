# mutation-testing-stryker

**Issue:** Measuring test suite quality by checking if tests catch code mutations
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
90% line coverage but tests still miss bugs. Mutation testing reveals tests that pass even when production code is deliberately broken.

## Pattern / Solution
```bash
npm install -D @stryker-mutator/core @stryker-mutator/jest-runner
```

`stryker.config.mjs`:
```js
export default {
  testRunner: "jest",
  reporters: ["html", "clear-text", "progress"],
  coverageAnalysis: "perTest",
  mutate: ["src/**/*.ts", "!src/**/*.test.ts"],
  thresholds: { high: 80, low: 60, break: 50 },
};
```

Run: `npx stryker run`

Stryker introduces mutations like:
- `x > y` → `x >= y`
- `return true` → `return false`
- `&&` → `||`

If tests still pass after mutation, the mutation is "survived" — tests are insufficient.

## Gotchas
- Mutation testing is slow — run overnight or on changed files only
- Focus on critical business logic first, not all code
- Use `--incremental` flag to only re-run changed mutations

## Related
- `test-coverage-meaningful-metrics.md`
- `tdd-workflow.md`
