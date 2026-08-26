# unit-test-arrange-act-assert

**Issue:** Unstructured test bodies are hard to read and maintain
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests with setup, action, and assertion interleaved are difficult to debug when they fail.

## Pattern / Solution
```ts
it("calculates discounted price for premium users", () => {
  // Arrange
  const user = { tier: "premium" };
  const product = { price: 100 };
  const service = new PricingService();

  // Act
  const price = service.calculate(user, product);

  // Assert
  expect(price).toBe(80);
});
```

For async tests:
```ts
it("sends welcome email on registration", async () => {
  // Arrange
  const mailer = vi.fn();
  const svc = new AuthService({ mailer });

  // Act
  await svc.register({ email: "a@b.com" });

  // Assert
  expect(mailer).toHaveBeenCalledWith("a@b.com", "welcome");
});
```

## Gotchas
- One logical assertion per test (can have multiple expect calls)
- Don't mix multiple acts in one test
- Teardown goes in afterEach, not in the test body

## Related
- `unit-test-test-doubles.md`
- `unit-test-naming-conventions.md`
