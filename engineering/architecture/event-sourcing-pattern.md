# event-sourcing-pattern

**Issue:** Storing state as an append-only log of events rather than current state
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Audit requirements need full history; current state alone cannot answer "why is it in this state?"

## Pattern / Solution
Events are the source of truth. Current state is derived by replaying events.

```
Events (append-only):
  OrderCreated { id, customer, at }
  ItemAdded    { id, product, qty, price, at }
  OrderPlaced  { id, at }
  ItemShipped  { id, tracking, at }

Reconstruct state:
  order = new Order()
  for event in event_store.get(order_id):
      order.apply(event)
```

Snapshots: periodically snapshot state so replay doesn't start from the beginning.

```
snapshot at event 1000 → replay only events 1001..current
```

## Gotchas
- Schema evolution of events is hard; events are immutable but their meaning can be upcasted
- Large event streams need snapshot strategy from day one
- Not suitable for simple CRUD with no audit or temporal query needs

## Related
- `cqrs-pattern.md`
- `domain-events.md`
- `outbox-pattern.md`
