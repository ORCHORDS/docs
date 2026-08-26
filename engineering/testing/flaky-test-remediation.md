# flaky-test-remediation

**Issue:** Fixing non-deterministic tests that pass and fail unpredictably
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A test identified as flaky keeps appearing in failure dashboards despite multiple "fix" attempts.

## Pattern / Solution
Address the root cause category:

**Timing / async:** Replace arbitrary `sleep` with proper awaiting of observable state.
```ts
// bad
await page.waitForTimeout(2000);
// good
await page.waitForSelector('[data-loaded="true"]');
```

**Shared state:** Ensure each test creates and destroys its own data; never rely on insertion order or leftover records.

**Random/date-dependent:** Seed PRNGs deterministically in test setup; freeze time with `jest.useFakeTimers` or `vi.useFakeTimers`.

**Network:** Use MSW or Playwright route interception so external calls are deterministic.

**File system:** Use `tmp` directories unique per test run; clean up in `afterEach`.

After fixing, add the test to a "formerly flaky" quarantine suite and run it 100 times in CI before removing the quarantine tag.

## Gotchas
- Retrying a flaky test in CI is a workaround, not a fix — it should only buy time while a real fix ships.
- Race conditions in parallel tests often masquerade as random failures.

## Related
- flaky-test-detection
- test-retry-strategies
- test-isolation-principles
