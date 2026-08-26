# shared-test-state-antipatterns

**Issue:** Common patterns that introduce hidden shared state between tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests that individually pass begin failing after adding unrelated tests, pointing to global state contamination.

## Pattern / Solution
Antipatterns to eliminate:

**Global singleton instances:**
```ts
// bad — one EventEmitter instance shared across all tests
const bus = new EventEmitter();
```
Fix: create a fresh instance in `beforeEach`.

**Module-level constants mutated in tests:**
```ts
// bad
let config = { retries: 3 };
test("...", () => { config.retries = 0; }); // leaks to next test
```
Fix: clone before mutating, or use `beforeEach` to reset.

**Database rows not cleaned up:**
Tests that insert rows without cleanup contaminate DB-dependent tests. Fix: use `transactional-test-rollback` or explicit `afterEach` deletes.

**Process environment variables:**
```ts
// bad
process.env.API_URL = "http://mock";
```
Fix: use `vi.stubEnv` / `jest.replaceProperty` which restores automatically.

**`console` / global timer patching without restore:**
Always pair `vi.spyOn(console, "error")` with `vi.restoreAllMocks()` in `afterEach`.

## Gotchas
- ESM module caching is harder to reset than CJS; prefer dependency injection over top-level imports for stateful modules.

## Related
- test-isolation-principles
- test-independence
- flaky-test-remediation
