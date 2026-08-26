# london-school-tdd

**Issue:** Understanding the mockist / interaction-based approach to TDD
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers familiar with state-based (Detroit) TDD struggle to apply the interaction-based London style, leading to either under-mocking or over-mocking.

## Pattern / Solution
London-school TDD (mockist style) focuses on verifying **collaborator interactions** rather than final state:

- Every dependency of the unit under test is replaced with a mock.
- Tests assert that the right messages were sent to collaborators with the right arguments.
- Design emerges by specifying the protocol between objects.

```ts
const emailService = { send: vi.fn() };
const orderService = new OrderService(emailService);

await orderService.complete(order);

expect(emailService.send).toHaveBeenCalledWith({
  to: order.email,
  template: "order-confirmed",
  orderId: order.id,
});
```

Best suited for systems with many collaborating objects where the key question is "did this object tell that object the right thing?"

## Gotchas
- Mocking everything tightly couples tests to implementation — refactoring often breaks tests even when behaviour is unchanged.
- Does not verify that collaborators actually do what mocks pretend they do; integration tests must fill this gap.
- Combine with contract tests to avoid mock drift.

## Related
- classic-tdd-detroit
- outside-in-tdd
- mocking-vs-stubbing-vs-spying
- contract-testing-pact
