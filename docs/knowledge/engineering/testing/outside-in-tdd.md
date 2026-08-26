# outside-in-tdd

**Issue:** Driving design from acceptance tests inward to unit tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Units are tested in isolation but the system never coheres — integration points are discovered late, leading to expensive rework.

## Pattern / Solution
Outside-in TDD (also called "double loop TDD") starts with a failing acceptance test, then writes unit tests for each collaborating component as needed:

1. Write a failing **acceptance test** for a user-observable outcome (E2E or integration level).
2. Identify the first object/module needed. Write a failing **unit test** for it.
3. Implement just enough to pass the unit test.
4. Move to the next collaborator; repeat unit-test cycle.
5. When all collaborators are implemented, the acceptance test goes green.

This approach drives interface design from the consumer's perspective, avoiding over-engineering of internals.

## Gotchas
- The acceptance test stays red for a long time during inner loops — that is expected.
- Mocking collaborators in the unit loop requires discipline; swap mocks for real implementations before the acceptance test can pass.
- Works best when acceptance tests are fast (integration-level) rather than full browser E2E.

## Related
- london-school-tdd
- tdd-workflow
- acceptance-test-driven-development
- bdd-cucumber-gherkin
