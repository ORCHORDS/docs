# aggregate-root-pattern

**Issue:** Maintaining consistency boundaries around clusters of related domain objects
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Invariants that span multiple entities are violated when any code can modify any entity directly.

## Pattern / Solution
An Aggregate is a cluster of objects treated as a unit for data changes. The Aggregate Root is the only entry point.

```python
class Order:  # Aggregate Root
    def __init__(self, id, customer_id):
        self.id = id
        self.customer_id = customer_id
        self._items = []  # OrderItem entities — private

    def add_item(self, product_id, qty, price):
        # enforces invariant: max 50 items
        if len(self._items) >= 50:
            raise DomainError("Order too large")
        self._items.append(OrderItem(product_id, qty, price))
        self._record_event(ItemAdded(self.id, product_id))
```

Rules:
- External code only holds references to the root, never to internal entities
- Only the root has a global identity; children have local identity within the aggregate
- One repository per aggregate root
- Aggregates communicate via domain events, not direct references

## Gotchas
- Large aggregates cause lock contention; keep them small
- Do not model aggregates by data shape alone; model by consistency boundary
- Lazy loading inside aggregates breaks invariant enforcement

## Related
- `domain-driven-design-basics.md`
- `repository-pattern-ddd.md`
- `domain-events.md`
