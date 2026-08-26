# test-reporting-junit

**Issue:** Generating JUnit XML reports for CI systems to parse test results
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CI platforms (Jenkins, GitLab, GitHub Actions with test-reporter) need a machine-readable format to display per-test pass/fail history and trend graphs.

## Pattern / Solution
All major frameworks support JUnit output:

**Vitest:**
```ts
// vitest.config.ts
reporters: ["verbose", ["junit", { outputFile: "test-results/junit.xml" }]],
```

**Jest:**
```bash
jest --reporters=default --reporters=jest-junit
# JEST_JUNIT_OUTPUT_DIR=test-results jest
```

**Playwright:**
```ts
reporter: [["junit", { outputFile: "test-results/results.xml" }]],
```

Upload the XML as a CI artifact and point the platform's test-results parser at it. For GitHub Actions use `dorny/test-reporter` action; for GitLab use the `junit` report type in `artifacts:reports`.

## Gotchas
- Some tools produce non-standard JUnit XML — validate with an online JUnit schema validator if parsing fails.
- Include timestamps and durations in reports so you can detect slowdowns over time.
- Merge multiple shard outputs with `junit-merge` or equivalent before uploading.

## Related
- ci-test-parallelization
- test-coverage-meaningful-metrics
- test-reporting-junit
