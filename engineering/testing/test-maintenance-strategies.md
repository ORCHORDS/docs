# test-maintenance-strategies

**Issue:** Keeping a test suite from becoming a burden as the codebase evolves
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The test suite grows to thousands of tests, half of which break whenever any refactoring happens, so developers stop refactoring.

## Pattern / Solution
**Delete tests that no longer add value.** A test that verifies internal implementation rather than observable behaviour should be removed, not updated, when the implementation changes.

**Treat test code as production code:**
- Apply the same linting rules.
- Extract shared setup into named helpers, not copy-pasted `beforeEach` blocks.
- Review test changes in PRs with the same scrutiny as production changes.

**Prune snapshot files regularly** — stale snapshots that are always updated without review erode confidence.

**Tag slow tests** and run them in a separate CI step so fast feedback is not blocked:
```ts
it.slow("heavy integration path", async () => { ... });
```

**Review test duplication** in the same retrospective as production duplication — duplicated tests mean duplicated maintenance burden.

## Gotchas
- The instinct to "just update the test" when it fails may be correct (test was wrong) or a sign of a regression (code changed behaviour unexpectedly). Always investigate before updating.
- Deleting tests requires confidence that behaviour is covered elsewhere or intentionally removed.

## Related
- test-organization-structure
- refactoring-with-tests
- legacy-code-testing
