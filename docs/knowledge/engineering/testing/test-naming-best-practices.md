# test-naming-best-practices

**Issue:** Writing test names that clearly communicate intent and make failures self-explanatory
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A failing CI build shows `✗ test 3` or `✗ should work correctly`, giving no indication of what broke or why.

## Pattern / Solution
Use the pattern **"[Unit] [action] [expected outcome]"** or natural language sentences:

```ts
// bad
it("works", ...);
it("test discount", ...);

// good
it("applies 10% discount when order total exceeds $100", ...);
it("throws InvalidCouponError when coupon has expired", ...);
it("returns an empty array when no results match the query", ...);
```

For `describe` blocks, name the subject (class, function, module):
```ts
describe("DiscountCalculator", () => {
  describe("when the cart total is above the threshold", () => {
    it("applies the configured percentage discount", ...);
    it("does not apply the discount twice", ...);
  });
});
```

The test name should read as a sentence: `DiscountCalculator when the cart total is above the threshold applies the configured percentage discount`.

## Gotchas
- Avoid implementation details in names ("calls calculateDiscount method") — prefer observable outcomes.
- Do not include the word "test" or "spec" in the name.
- Updating names when behaviour changes is as important as updating assertions.

## Related
- unit-test-naming-conventions
- test-organization-structure
- tdd-workflow
