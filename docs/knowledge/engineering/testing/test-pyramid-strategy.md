# test-pyramid-strategy

**Issue:** Choosing the right ratio of unit, integration, and e2e tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams either write only e2e tests (slow, brittle) or only unit tests (fast but miss integration bugs). The test pyramid guides the right distribution.

## Pattern / Solution
```
        /\
       /e2e\        <- few, expensive, slow
      /------\
     / integr \     <- moderate number
    /----------\
   /   unit     \   <- many, cheap, fast
  /______________\
```
Typical ratio: 70% unit, 20% integration, 10% e2e.

Unit tests: pure functions, business logic, components in isolation.
Integration tests: API routes, DB queries, multi-module workflows.
E2e tests: critical user journeys only (login, checkout, signup).

## Gotchas
- Ice-cream cone anti-pattern: inverted pyramid, too many e2e
- Don't count coverage lines — count confidence per layer
- Integration tests that mock everything are just unit tests in disguise

## Related
- `unit-test-what-to-test.md`
- `end-to-end-test-strategy.md`
- `integration-test-api.md`
