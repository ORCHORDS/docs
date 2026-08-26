# feature-cookbook-state-machines

**Issue:** State machines — orders, subscriptions, workflows
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have an order. The user pays. You set the status to
"paid." You ship. You set the status to "shipped." The
user returns the order. You set the status to "returned."
You refund. You set the status to "refunded." The user
calls: "My order is in 'paid' but I returned it." You look
at the code. The status is "refunded." But the user is
right — the system says "paid" somewhere. The states are
inconsistent.

## Root cause
**Statuses are set ad-hoc.** Without a state machine,
any state can transition to any other state.

**Source:** State machine docs.

## The "state machine" pattern

For a clear state machine, define the states + transitions:
```ts
type OrderStatus = 'pending' | 'paid' | 'shipped' | 'delivered' | 'returned' | 'refunded' | 'cancelled';

const TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  pending: ['paid', 'cancelled'],
  paid: ['shipped', 'cancelled', 'refunded'],  // Pre-ship refund
  shipped: ['delivered', 'returned'],
  delivered: ['returned'],
  returned: ['refunded'],
  refunded: [],  // Terminal
  cancelled: [],  // Terminal
};

function canTransition(from: OrderStatus, to: OrderStatus): boolean {
  return TRANSITIONS[from]?.includes(to) ?? false;
}

function transition(order: Order, to: OrderStatus): Order {
  if (!canTransition(order.status, to)) {
    throw new Error(`Invalid transition: ${order.status} -> ${to}`);
  }
  return { ...order, status: to, updatedAt: new Date().toISOString() };
}
```

The state machine enforces valid transitions.

## The "XState" pattern

For a more complex state machine, use XState:
```ts
import { createMachine, interpret } from 'xstate';

const orderMachine = createMachine({
  id: 'order',
  initial: 'pending',
  states: {
    pending: {
      on: { PAID: 'paid', CANCEL: 'cancelled' },
    },
    paid: {
      on: { SHIP: 'shipped', REFUND: 'refunded' },
    },
    shipped: {
      on: { DELIVER: 'delivered', RETURN: 'returned' },
    },
    delivered: {
      on: { RETURN: 'returned' },
    },
    returned: {
      on: { REFUND: 'refunded' },
    },
    refunded: { type: 'final' },
    cancelled: { type: 'final' },
  },
});

const service = interpret(orderMachine).start();
service.send('PAID');  // { value: 'paid', ... }
```

XState handles complex state machines.

## The "database state machine" pattern

For a DB state machine:
```sql
CREATE TABLE orders (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'shipped', 'delivered', 'returned', 'refunded', 'cancelled')),
  -- ...
);
```

The CHECK constraint enforces the valid states.

## The "transition log" pattern

For an audit trail, log every transition:
```sql
CREATE TABLE order_transitions (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  reason TEXT,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
```

The history is queryable.

## The "guard" pattern

For conditional transitions:
```ts
function canShip(order: Order): boolean {
  return order.paymentStatus === 'paid' && order.address !== null;
}

if (!canShip(order)) {
  throw new Error('Cannot ship: payment not received or address missing');
}
```

The transition is guarded.

## The "side effect" pattern

For side effects on transition:
```ts
async function shipOrder(order: Order, env: Env): Promise<Order> {
  // 1. Transition
  const updated = transition(order, 'shipped');

  // 2. Side effects
  await env.DB!.prepare(
    `UPDATE orders SET status = ?, shipped_at = ?, tracking_number = ? WHERE id = ?`
  ).bind('shipped', new Date().toISOString(), generateTrackingNumber(), order.id).run();

  // 3. Notify the user
  await sendEmail({
    to: order.userEmail,
    subject: 'Your order has shipped',
    html: `Track your order: ${generateTrackingUrl(order.trackingNumber)}`,
  }, env);

  return updated;
}
```

The side effects are part of the transition.

## The "subscription state" pattern

For a subscription:
```ts
type SubscriptionStatus = 'active' | 'past_due' | 'cancelled' | 'expired';

const TRANSITIONS: Record<SubscriptionStatus, SubscriptionStatus[]> = {
  active: ['past_due', 'cancelled'],
  past_due: ['active', 'cancelled', 'expired'],
  cancelled: ['expired'],
  expired: [],  // Terminal
};
```

The subscription follows a state machine.

## The "approval workflow" pattern

For an approval workflow:
```ts
type ApprovalStatus = 'draft' | 'pending_review' | 'approved' | 'rejected';

const TRANSITIONS: Record<ApprovalStatus, ApprovalStatus[]> = {
  draft: ['pending_review'],
  pending_review: ['approved', 'rejected'],
  approved: [],  // Terminal
  rejected: ['draft'],  // Re-edit
};
```

The approval follows a state machine.

## The "workflow engine" pattern

For complex workflows, use a workflow engine:
- **Temporal:** https://temporal.io/
- **Cadence:** https://cadenceworkflow.io/
- **Step Functions (AWS):** https://aws.amazon.com/step-functions/

These handle long-running, retrying, multi-step workflows.

## The "state machine" anti-patterns

### 1. Boolean flags
- **Issue:** A row with `is_paid: true, is_shipped: false` is
  ambiguous (refunded? cancelled?)
- **Fix:** Use a single `status` field

### 2. No transitions
- **Issue:** Any state can go to any state
- **Fix:** Define valid transitions

### 3. No audit log
- **Issue:** No record of who changed the status when
- **Fix:** Log every transition

### 4. Side effects in the transition
- **Issue:** Hard to test; race conditions
- **Fix:** Separate the transition from the side effects
  (or use a workflow engine)

### 5. No terminal states
- **Issue:** A "refunded" order can be re-shipped
- **Fix:** Define terminal states (no outgoing transitions)

## The "state machine" verification

- **Test:** Valid transitions work
- **Test:** Invalid transitions throw
- **Test:** Side effects fire on transition
- **Test:** The audit log captures every transition
- **Audit:** Annual review of state machines

## Gotchas
- **The "boolean flags" anti-pattern.** Use a single
  status field.
- **The "no transitions" anti-pattern.** Define valid
  transitions.
- **The "no terminal states" anti-pattern.** A terminal
  state prevents re-processing.
- **The "no audit log" anti-pattern.** Without a log,
  you can't debug.

## Related
- `feature-cookbook.md`
- `event-sourcing.md`
- `audit-log-as-product.md`
- `saga-pattern.md`
- `idempotency-keys.md`
- `webhook-implementation.md`
- XState: https://xstate.js.org/
- Temporal: https://temporal.io/
