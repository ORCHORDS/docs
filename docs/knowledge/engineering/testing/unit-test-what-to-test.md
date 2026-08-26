# unit-test-what-to-test

**Issue:** Deciding which code units deserve unit tests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers test implementation details (private methods, internal state) instead of behavior, leading to fragile tests that break on every refactor.

## Pattern / Solution
Test public behavior, not implementation:
```ts
// BAD: testing implementation detail
expect(service._cache.size).toBe(1);

// GOOD: testing observable behavior
const result = await service.getUser(id);
expect(result.name).toBe("Alice");
```

Good candidates for unit tests:
- Pure functions with complex logic
- Utility/helper functions
- Business rule validators
- State machines and reducers
- Error handling branches

## Gotchas
- Private methods get tested through public API
- Don't test third-party libraries
- Avoid testing trivial getters/setters with no logic

## Related
- `unit-test-naming-conventions.md`
- `unit-test-arrange-act-assert.md`
- `test-pyramid-strategy.md`
