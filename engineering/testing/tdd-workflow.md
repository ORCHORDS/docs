# tdd-workflow

**Issue:** Applying the red-green-refactor cycle consistently in day-to-day development
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers write tests after code, making tests conform to the implementation rather than the desired behaviour, and miss edge cases discovered during test-first thinking.

## Pattern / Solution
The TDD cycle:

1. **Red** — Write the smallest failing test that describes one new behaviour. Run it; confirm it fails for the right reason.
2. **Green** — Write the minimum production code to make the test pass. No gold-plating.
3. **Refactor** — Clean up both production and test code while keeping tests green.

Practical cadence:
- One failing test at a time; do not write a second test until the first is green.
- Commit at every green state so you have a known-good rollback point.
- The test file is the specification — name tests as sentences describing behaviour, not implementation.

```ts
describe("ShoppingCart", () => {
  it("starts empty", () => { /* red → green → refactor */ });
  it("adds an item", () => { });
  it("calculates total with tax", () => { });
});
```

## Gotchas
- TDD does not replace design thinking — sketch the interface before writing the first test.
- Skipping the refactor step accumulates test debt as fast as production debt.
- TDD works best for algorithmic and domain logic; pure UI layout is harder to drive this way.

## Related
- unit-test-arrange-act-assert
- outside-in-tdd
- classic-tdd-detroit
- london-school-tdd
