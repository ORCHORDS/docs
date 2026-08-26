# classic-tdd-detroit

**Issue:** Applying state-based TDD without excessive mocking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests become fragile because every collaborator is mocked, making refactoring painful. The Detroit (classicist) approach avoids this by testing real objects together.

## Pattern / Solution
Classic TDD uses real implementations wherever practical, replacing only external dependencies (databases, HTTP clients, clocks):

- Prefer real objects; introduce test doubles only at the system boundary.
- Verify observable **state** after exercising behaviour, not which methods were called.
- Refactoring internals does not break tests as long as outcomes are the same.

```ts
const cart = new ShoppingCart();
cart.add({ sku: "A1", price: 10, qty: 2 });
cart.add({ sku: "B2", price: 5,  qty: 1 });

expect(cart.total()).toBe(25);
expect(cart.itemCount()).toBe(3);
```

No mocks needed — the collaborators (`PriceCalculator`, `Inventory`) use real implementations with in-memory stores seeded for the test.

## Gotchas
- Real objects that call external services must still be seeded or wrapped with test-friendly adapters.
- In-memory implementations of repositories or services must mirror production behaviour exactly or they create false confidence.
- Classicist tests can be slower than mockist tests when real objects do real work.

## Related
- london-school-tdd
- tdd-workflow
- test-isolation-principles
