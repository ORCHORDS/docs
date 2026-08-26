# bdd-cucumber-gherkin

**Issue:** Writing human-readable acceptance tests using Gherkin syntax with Cucumber
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Non-technical stakeholders cannot read or verify unit tests, leading to misalignment between requirements and implementation.

## Pattern / Solution
Gherkin scenarios live in `.feature` files and are executed by step definitions:

```gherkin
# features/checkout.feature
Feature: Checkout

  Scenario: Guest completes purchase
    Given a guest with items in the cart
    When the guest provides valid payment details
    Then the order is confirmed
    And an email receipt is sent
```

Step definitions in TypeScript (with `@cucumber/cucumber`):

```ts
import { Given, When, Then } from "@cucumber/cucumber";

Given("a guest with items in the cart", async function () {
  this.cart = await Cart.createWithItems([{ sku: "abc", qty: 1 }]);
});
When("the guest provides valid payment details", async function () {
  this.result = await this.cart.checkout({ card: testCard });
});
Then("the order is confirmed", function () {
  expect(this.result.status).toBe("confirmed");
});
```

Keep scenarios focused on user-observable outcomes, not on UI mechanics.

## Gotchas
- Gherkin is not a silver bullet — over-specified feature files become maintenance burdens.
- Prefer declarative ("the user is logged in") over imperative ("clicks the login button") step phrasing.
- Step libraries shared across many feature files become fragile; favour small, composable steps.

## Related
- acceptance-test-driven-development
- tdd-workflow
- outside-in-tdd
