# refactoring-with-tests

**Issue:** Using tests as a safety net while restructuring existing code
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers avoid refactoring because they fear breaking untested code paths, resulting in mounting technical debt.

## Pattern / Solution
Before refactoring:
1. **Ensure coverage:** If tests are sparse, write characterization tests (see characterization-tests) to document current behaviour.
2. **Run the suite in watch mode** during refactoring to get immediate feedback.
3. **Commit at every green state** — small, reversible steps.

Refactoring workflow:
```bash
# 1. all green
vitest run

# 2. extract/rename/reorganise — keep tests green
# 3. commit
git commit -m "refactor: extract PaymentValidator from OrderService"
# 4. next step
```

Use IDE refactoring tools (rename, extract method, move) instead of manual find-and-replace — they update call sites automatically.

After refactoring, delete any tests that were only written to cover internal implementation details that no longer exist.

## Gotchas
- Refactoring changes structure, not behaviour. If a test fails after a refactor, either the refactor changed behaviour (revert) or the test was testing internals (update the test).
- Do not refactor and add features in the same commit — it makes diffs unreadable and makes bisecting failures harder.

## Related
- characterization-tests
- legacy-code-testing
- tdd-workflow
- test-maintenance-strategies
