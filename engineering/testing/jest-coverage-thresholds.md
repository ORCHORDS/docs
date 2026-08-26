# jest-coverage-thresholds

**Issue:** Enforcing minimum coverage without making it a vanity metric
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Coverage is 90% but critical paths are untested. Or thresholds are set so low they provide no protection.

## Pattern / Solution
```ts
// jest.config.ts
coverageThreshold: {
  global: {
    branches: 80,
    functions: 85,
    lines: 85,
    statements: 85,
  },
  // Per-file thresholds for critical modules
  "./src/billing/": {
    branches: 95,
    functions: 95,
    lines: 95,
    statements: 95,
  },
},
coverageProvider: "v8", // or "babel"
```

Run coverage: `jest --coverage`
Exclude files: add `!src/**/*.types.ts` to `collectCoverageFrom`.

## Gotchas
- 100% coverage does not mean all edge cases are tested
- `branch` coverage is more meaningful than `line` coverage
- Generated files (protobuf, graphql codegen) should be excluded

## Related
- `test-coverage-meaningful-metrics.md`
- `vitest-coverage-v8.md`
