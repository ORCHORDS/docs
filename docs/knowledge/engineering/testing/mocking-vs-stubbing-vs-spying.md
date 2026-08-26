# mocking-vs-stubbing-vs-spying

**Issue:** Conflating mocks, stubs, and spies leads to incorrect test design
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Using `jest.mock()` everywhere when you only need return values, or forgetting to assert on mock expectations.

## Pattern / Solution
```ts
// STUB: control return value, do not assert calls
const emailService = { send: jest.fn().mockResolvedValue(undefined) };

// SPY: wrap real implementation, assert calls
import * as utils from "./utils";
const spy = jest.spyOn(utils, "formatDate");
processOrder(order);
expect(spy).toHaveBeenCalledWith(order.date);
spy.mockRestore();

// MOCK: strict expectation — verify interaction
const mockRepo = {
  save: jest.fn().mockResolvedValue({ id: "123" }),
};
await service.createUser(data);
expect(mockRepo.save).toHaveBeenCalledWith(expect.objectContaining({ email: data.email }));
```

Rule of thumb: stub queries (return values), mock commands (verify calls).

## Gotchas
- `jest.spyOn` modifies the original module — always restore
- Mocks without assertions give false confidence
- Over-mocking makes tests useless as regression detectors

## Related
- `unit-test-test-doubles.md`
- `jest-module-mocking.md`
