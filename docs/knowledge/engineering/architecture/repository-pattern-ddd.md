# repository-pattern-ddd

**Issue:** Abstracting persistence behind a collection-like interface for domain objects
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Domain logic becomes entangled with SQL queries; switching storage or testing is painful.

## Pattern / Solution
Repository provides a collection interface; implementation details stay out of the domain.

```python
# Domain layer — pure interface
class OrderRepository(ABC):
    @abstractmethod
    def get(self, order_id: str) -> Order: ...
    @abstractmethod
    def save(self, order: Order) -> None: ...
    @abstractmethod
    def find_by_customer(self, customer_id: str) -> list[Order]: ...

# Infrastructure layer — SQL implementation
class SqlOrderRepository(OrderRepository):
    def get(self, order_id):
        row = self.db.query("SELECT * FROM orders WHERE id = %s", order_id)
        return self._to_domain(row)

    def save(self, order):
        self.db.upsert("orders", self._to_record(order))
        # also save events if using outbox
```

One repository per aggregate root. Repositories deal only in aggregate roots, not raw entities.

## Gotchas
- Avoid generic repositories (`Repository<T>`) — they leak query concerns into domain
- Keep queries out of the repository interface; use a separate query service or read model
- Repository.save() implies both insert and update — use upsert or check existence

## Related
- `aggregate-root-pattern.md`
- `cqrs-pattern.md`
- `hexagonal-architecture.md`
