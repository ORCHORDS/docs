# test-independence

**Issue:** Making tests runnable in any order without implicit dependencies between them
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A new team member runs a single failing test, fixes it, and it passes in isolation but fails when the suite runs — because a previous test set up state this test silently relied on.

## Pattern / Solution
**Self-contained test setup:** Every test creates its own data and tears it down, never borrowing from siblings.

**Randomise test order in CI** to surface hidden dependencies:

```bash
# Jest
jest --randomize

# Vitest
vitest run --sequence.shuffle
```

**Detect ordering issues locally** by running a reversed or randomised order on every PR.

Use factory helpers rather than shared fixtures:

```ts
// bad — relies on test order
let user: User;
beforeAll(() => { user = createUser(); }); // shared across describe block

// good
function makeUser(overrides = {}) {
  return createUser({ email: `u${Date.now()}@test.com`, ...overrides });
}
```

## Gotchas
- Random ordering exposes flakiness but can also mask it if a specific ordering is never hit — use a seed that is logged so failures can be reproduced.
- Parallelism and randomisation are different axes; both should be enabled.

## Related
- test-isolation-principles
- shared-test-state-antipatterns
- flaky-test-detection
