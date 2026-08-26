# test-organization-structure

**Issue:** Arranging test files and directories so they are easy to navigate and maintain
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
As the codebase grows, tests are scattered, duplicated, or hard to locate, leading to gaps and redundant coverage.

## Pattern / Solution
Two common conventions — choose one and be consistent:

**Co-located (preferred for unit tests):**
```
src/
  cart/
    cart.ts
    cart.test.ts       # alongside the source
    cart.spec.ts       # alternatively
```

**Centralised (preferred for integration / E2E):**
```
tests/
  unit/
  integration/
  e2e/
```

Within a test file, mirror the structure of the module under test:

```ts
describe("CartService", () => {
  describe("add()", () => { ... });
  describe("remove()", () => { ... });
  describe("checkout()", () => {
    describe("with a valid payment method", () => { ... });
    describe("with an expired card", () => { ... });
  });
});
```

Keep helper utilities in a `__tests__/helpers/` or `tests/support/` directory, never inline in test files.

## Gotchas
- Do not create a single test file per module mechanically — group by behaviour, not file structure.
- Deeply nested `describe` blocks beyond three levels become hard to read; extract to separate files.

## Related
- test-naming-best-practices
- test-maintenance-strategies
- test-fixtures-patterns
