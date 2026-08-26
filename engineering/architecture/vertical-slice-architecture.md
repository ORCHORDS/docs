# vertical-slice-architecture

**Issue:** Organizing code by feature rather than technical layer to reduce cross-cutting coordination
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Adding a feature requires touching controllers, services, repositories, and DB migrations in different folders; PRs are huge.

## Pattern / Solution
Each feature owns its full vertical slice: handler, logic, data access, and tests.

```
features/
  place-order/
    PlaceOrderCommand.ts
    PlaceOrderHandler.ts   ← all logic here
    PlaceOrderValidator.ts
    place-order.sql        ← or ORM query
    place-order.test.ts
  cancel-order/
    CancelOrderCommand.ts
    CancelOrderHandler.ts
    ...
shared/
  events/
  middleware/
```

Each handler receives a command, does its work, and returns a result. No shared service layer.

## Gotchas
- Code duplication is acceptable within slices; sharing is opt-in, not default
- Cross-slice communication via events, not direct calls
- Works best with a mediator/dispatcher to route commands to handlers

## Related
- `cqrs-pattern.md`
- `clean-architecture-layers.md`
- `domain-events.md`
