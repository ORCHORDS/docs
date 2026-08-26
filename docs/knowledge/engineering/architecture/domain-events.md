# domain-events

**Issue:** Decoupling side effects from domain logic using explicit event types
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A method like `place_order()` grows to 200 lines because it handles email, inventory, analytics, and payments inline.

## Pattern / Solution
Domain events are immutable records of something that happened in the domain.

```python
@dataclass(frozen=True)
class OrderPlaced:
    order_id: str
    customer_id: str
    total: Decimal
    occurred_at: datetime

class Order:
    def place(self):
        # business logic only
        self.status = OrderStatus.PLACED
        self._events.append(OrderPlaced(self.id, self.customer_id, self.total, now()))

# Application service dispatches events after commit
class PlaceOrderService:
    def execute(self, cmd):
        order = self.repo.get(cmd.order_id)
        order.place()
        self.repo.save(order)
        for event in order.pull_events():
            self.event_bus.publish(event)
```

## Gotchas
- Publish events after DB commit, not before (use outbox pattern for reliability)
- Domain events differ from integration events: domain events are internal, integration events cross service boundaries
- Event schemas must be versioned from day one

## Related
- `aggregate-root-pattern.md`
- `outbox-pattern.md`
- `event-sourcing-pattern.md`
