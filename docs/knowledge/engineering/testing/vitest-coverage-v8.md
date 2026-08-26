# vitest-coverage-v8

**Issue:** Configuring V8-based coverage in Vitest for accurate branch reporting
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Istanbul (babel) coverage misreports coverage on TypeScript code that uses type-level constructs. V8 coverage is more accurate.

## Pattern / Solution
```bash
npm install -D @vitest/coverage-v8
```

`vitest.config.ts`:
```ts
test: {
  coverage: {
    provider: "v8",
    reporter: ["text", "html", "lcov", "json-summary"],
    reportsDirectory: "./coverage",
    include: ["src/**/*.ts", "src/**/*.tsx"],
    exclude: [
      "src/**/*.d.ts",
      "src/**/*.stories.tsx",
      "src/test/**",
    ],
    thresholds: {
      lines: 80,
      branches: 75,
      functions: 80,
      statements: 80,
    },
    all: true, // report uncovered files
  },
}
```

Run: `vitest run --coverage`

## Gotchas
- V8 coverage requires Node 18+
- `all: true` shows files with 0% coverage — important for spotting gaps
- `lcov` format integrates with Codecov, Coveralls, SonarQube

## Related
- `jest-coverage-thresholds.md`
- `test-coverage-meaningful-metrics.md`
