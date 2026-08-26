# test-driven-development-workflow

**Issue:** Tests are written after the fact, making them feel like chores and leaving gaps in coverage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers write the feature, then add tests to "get coverage up." The tests verify what the code does, not what it should do. Bugs in the implementation are baked into the tests. Refactoring is painful because tests are tightly coupled to internals.

## Pattern / Solution
Test-Driven Development (TDD) inverts the order: write a failing test, write the minimum code to make it pass, refactor.

**Red-Green-Refactor cycle:**
```
RED:     Write a failing test that describes the desired behavior
GREEN:   Write the minimum production code to make the test pass
REFACTOR: Clean up code and tests without changing behavior
         → all tests still pass after refactor
REPEAT
```

**Practical micro-workflow:**
1. Read the acceptance criteria
2. Write one test for the simplest, most important case
3. Run — confirm it fails with a clear message (not an error)
4. Write just enough code to make it pass
5. Run — confirm green
6. Refactor both code and test
7. Pick the next case; repeat

**What to test first (priority order):**
1. The happy path (expected behavior)
2. Boundary conditions (empty input, zero, max value)
3. Error cases (invalid input, network failure)
4. Edge cases specific to the domain

**Where TDD works best:**
- Business logic and domain models
- Data transformations and parsers
- State machines
- Algorithm implementations

**Where TDD is harder:**
- UI rendering (use component tests + manual verification)
- Integration with external services (use contract tests)
- Exploratory code where requirements are unknown

## Gotchas
- TDD does not mean 100% coverage — it means writing tests before code, not maximizing a metric
- Tests must fail for the right reason — if a test passes on the first write, it's not testing anything
- Don't skip the refactor step; it's where design improvement happens

## Related
- `behaviour-driven-development-gherkin.md`
- `definition-of-done-checklist.md`
- `shift-left-security-testing.md`
