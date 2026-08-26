# saga-pattern-orchestration

**Issue:** Centralizing distributed transaction coordination for visibility and control
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Choreography sagas become impossible to reason about as the number of steps grows.

## Pattern / Solution
An orchestrator (workflow engine or state machine) commands each participant.

```
Orchestrator (OrderSaga):
  State: PENDING
  1. Command PaymentService: Charge(orderId, amount)
  2. Wait for PaymentCharged event
  3. Command InventoryService: Reserve(orderId, items)
  4. Wait for StockReserved event
  5. Command ShippingService: CreateShipment(orderId)
  6. State: COMPLETED

Failure handling:
  On PaymentFailed: State → FAILED (no compensation needed)
  On StockUnavailable: Command PaymentService: Refund → State → COMPENSATED
```

Workflow engines: Temporal, AWS Step Functions, Conductor, Camunda.

## Gotchas
- Orchestrator becomes a bottleneck and single point of failure; make it stateful/recoverable
- Avoid putting business logic in the orchestrator — it orchestrates, domain services decide
- Orchestrator coupling: services must respond to commands from the orchestrator

## Related
- `saga-pattern-choreography.md`
- `workflow-orchestration-patterns.md`
- `outbox-pattern.md`
