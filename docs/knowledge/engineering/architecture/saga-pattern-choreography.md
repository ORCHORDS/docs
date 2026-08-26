# saga-pattern-choreography

**Issue:** Managing distributed transactions across services without two-phase commit
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A business process spans multiple services (order, payment, inventory) and must handle partial failures.

## Pattern / Solution
Choreography-based saga: each service listens for events and decides what to do next.

```
1. OrderService emits OrderCreated
2. PaymentService listens → charges card → emits PaymentProcessed
3. InventoryService listens → reserves stock → emits StockReserved
4. ShippingService listens → creates shipment

Failure path:
  PaymentFailed → OrderService listens → emits OrderCancelled
  StockUnavailable → PaymentService listens → refunds → emits RefundIssued
```

Each step has a compensating transaction for rollback.

## Gotchas
- Difficult to see the overall flow; no central coordinator
- Cyclic event dependencies are hard to debug
- Compensating transactions must be idempotent and reliable

## Related
- `saga-pattern-orchestration.md`
- `event-driven-architecture.md`
- `outbox-pattern.md`
