# characterization-tests

**Issue:** Documenting what existing code actually does before changing it
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A legacy function produces output that no one fully understands. Changing it risks breaking downstream consumers in unpredictable ways.

## Pattern / Solution
A characterization test captures the current (possibly surprising) output without judging correctness:

```ts
// Characterizing formatPrice before refactoring
it("formats negative prices with a leading minus sign (current behaviour)", () => {
  expect(formatPrice(-5)).toBe("-$5.00");
  // NOTE: this may be a bug — document it before fixing
});

it("returns 'FREE' for zero price (current behaviour)", () => {
  expect(formatPrice(0)).toBe("FREE");
});
```

Steps:
1. Call the unit under test with representative inputs.
2. Record whatever it outputs — even if it seems wrong.
3. Make the test assert those exact outputs.
4. Now you can refactor safely; any change to behaviour will break a characterization test.

Label characterization tests clearly so future developers know they document current behaviour, not intended design.

## Gotchas
- Characterization tests are not regression tests — they capture bugs too. Fix the bug, update the test, and document the change.
- Use a separate `__characterization__` directory or tag so they do not clutter the main suite.

## Related
- legacy-code-testing
- golden-master-testing
- approval-testing
- refactoring-with-tests
