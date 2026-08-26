# test-retry-strategies

**Issue:** Deciding when and how to retry failing tests in CI without masking real failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams add automatic retries to all tests to reduce red builds, but this hides genuine regressions and inflates pipeline time.

## Pattern / Solution
Apply retries selectively and at the right layer:

**Framework-level retries (last resort for known-flaky):**
```ts
// playwright.config.ts
retries: process.env.CI ? 2 : 0,

// jest.config.ts
testRetries: 1, // jest-circus only
```

**Test-level annotation (Playwright):**
```ts
test("known flaky network call", { retries: 3 }, async ({ page }) => { ... });
```

**CI-level rerun:** Only rerun failed jobs, not the full suite. Store and re-use previously passed shard results.

Retries should be a temporary bridge while fixes are being developed. Track the retry rate in your test analytics dashboard — if it climbs above 5% of runs, prioritise remediation.

## Gotchas
- Retries with shared DB state can make a broken test appear to pass on the second attempt by picking up state left by the first run.
- Set a maximum retry count (2–3); unlimited retries can cause pipelines to run indefinitely.
- Log retry attempts explicitly so they are visible in CI output.

## Related
- flaky-test-detection
- flaky-test-remediation
- ci-test-parallelization
