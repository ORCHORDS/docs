# Event Bridge Pattern with Cloudflare Workers and Queues: Content-Based Routing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Multiple producers emit heterogeneous events (order placed, payment failed, user signed up) onto a single inbound channel. Downstream consumers care only about their own subset. Wiring each producer to each consumer creates an N×M coupling. You want a central routing layer — an event bridge — that inspects each event, classifies it, and delivers it to the correct consumer queue.

---

## Context

An event bridge is a message router that applies **content-based routing**: it reads the message, evaluates rules, and forwards to one or more target queues. Unlike pub/sub fan-out (which delivers to all subscribers), a bridge routes selectively.

In Cloudflare Workers:
- A single **bridge Worker** consumes from `queue-inbound`
- It evaluates routing rules against the event envelope
- It publishes to named target queues via producer bindings

This keeps producers decoupled from consumers; adding a new consumer means adding a routing rule, not modifying producers.

```
[OrderService]  ──┐
[PaymentService]──┼──► queue-inbound ──► Bridge Worker ──► queue-orders
[UserService]   ──┘                                    ──► queue-payments
                                                        ──► queue-users
                                                        ──► queue-dlq
```

---

## Event Envelope Schema

```typescript
// types/event.ts
export type EventType =
  | 'order.placed'
  | 'order.cancelled'
  | 'payment.succeeded'
  | 'payment.failed'
  | 'user.signed_up'
  | 'user.deleted';

export interface EventEnvelope<T = unknown> {
  id: string;
  type: EventType;
  version: string;       // e.g. "1.0"
  source: string;        // originating service
  timestamp: string;     // ISO-8601
  correlationId?: string;
  payload: T;
}
```

---

## Routing Rule Engine

```typescript
// bridge/src/rules.ts
import { EventEnvelope, EventType } from '../../types/event';

export type TargetBinding =
  | 'QUEUE_ORDERS'
  | 'QUEUE_PAYMENTS'
  | 'QUEUE_USERS'
  | 'QUEUE_DLQ';

interface RoutingRule {
  name: string;
  match: (event: EventEnvelope) => boolean;
  targets: TargetBinding[];
}

export const ROUTING_RULES: RoutingRule[] = [
  {
    name: 'order-events',
    match: e => e.type.startsWith('order.'),
    targets: ['QUEUE_ORDERS'],
  },
  {
    name: 'payment-events',
    match: e => e.type.startsWith('payment.'),
    targets: ['QUEUE_PAYMENTS'],
  },
  {
    name: 'user-events',
    match: e => e.type.startsWith('user.'),
    targets: ['QUEUE_USERS'],
  },
  {
    // Cross-cutting: payment failure also triggers order consumer
    name: 'payment-failure-order-impact',
    match: e => e.type === 'payment.failed',
    targets: ['QUEUE_ORDERS'],
  },
];

export function resolveTargets(event: EventEnvelope): TargetBinding[] {
  const matched = ROUTING_RULES.filter(rule => rule.match(event));

  if (matched.length === 0) {
    console.warn(`[bridge] No rule matched event type=${event.type}; routing to DLQ`);
    return ['QUEUE_DLQ'];
  }

  // Deduplicate targets (e.g. payment.failed matches both order and payment rules)
  return [...new Set(matched.flatMap(r => r.targets))];
}
```

---

## Bridge Worker

```typescript
// bridge/src/index.ts
import { Env } from './types';
import { EventEnvelope } from '../../types/event';
import { resolveTargets, TargetBinding } from './rules';

function getQueue(env: Env, binding: TargetBinding): Queue {
  const map: Record<TargetBinding, Queue> = {
    QUEUE_ORDERS: env.QUEUE_ORDERS,
    QUEUE_PAYMENTS: env.QUEUE_PAYMENTS,
    QUEUE_USERS: env.QUEUE_USERS,
    QUEUE_DLQ: env.QUEUE_DLQ,
  };
  return map[binding];
}

export default {
  async queue(batch: MessageBatch<EventEnvelope>, env: Env): Promise<void> {
    // Group sends by target queue to use sendBatch efficiently
    const pending = new Map<TargetBinding, EventEnvelope[]>();

    for (const msg of batch.messages) {
      const event = msg.body;
      const targets = resolveTargets(event);

      for (const target of targets) {
        if (!pending.has(target)) pending.set(target, []);
        pending.get(target)!.push(event);
      }

      msg.ack();
    }

    // Fan out to target queues in parallel
    await Promise.all(
      [...pending.entries()].map(([target, events]) =>
        getQueue(env, target).sendBatch(
          events.map(e => ({ body: e, contentType: 'json' }))
        )
      )
    );
  },
};
```

---

## Priority Routing Override

Sometimes high-severity events need to bypass normal routing latency. Add a priority rule that also routes to a dedicated high-priority queue:

```typescript
// bridge/src/rules.ts (addition)
export const PRIORITY_RULES: RoutingRule[] = [
  {
    name: 'critical-payment-failure',
    match: e => e.type === 'payment.failed' &&
                (e.payload as { amount: number }).amount > 10_000,
    targets: ['QUEUE_PAYMENTS_PRIORITY'],
  },
];

export function resolveTargets(event: EventEnvelope): TargetBinding[] {
  const allRules = [...ROUTING_RULES, ...PRIORITY_RULES];
  const matched = allRules.filter(rule => rule.match(event));

  if (matched.length === 0) return ['QUEUE_DLQ'];
  return [...new Set(matched.flatMap(r => r.targets))];
}
```

---

## Dead Letter Re-routing with Metadata

```typescript
// bridge/src/dlq-router.ts
// Consumes from queue-dlq, attaches routing metadata, alerts

import { Env } from './types';
import { EventEnvelope } from '../../types/event';

interface DLQEntry {
  event: EventEnvelope;
  reason: string;
  failedAt: string;
}

export default {
  async queue(batch: MessageBatch<DLQEntry>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const entry = msg.body;
      console.error(JSON.stringify({
        level: 'ERROR',
        msg: 'Event routed to DLQ',
        eventId: entry.event.id,
        eventType: entry.event.type,
        reason: entry.reason,
        failedAt: entry.failedAt,
      }));
      msg.ack();
    }
  },
};
```

---

## Wrangler Configuration

```toml
# bridge/wrangler.toml
name = "event-bridge"

[[queues.consumers]]
queue = "events-inbound"
max_batch_size = 250
max_batch_timeout = 2
max_retries = 3

[[queues.producers]]
binding = "QUEUE_ORDERS"
queue = "events-orders"

[[queues.producers]]
binding = "QUEUE_PAYMENTS"
queue = "events-payments"

[[queues.producers]]
binding = "QUEUE_USERS"
queue = "events-users"

[[queues.producers]]
binding = "QUEUE_DLQ"
queue = "events-dlq"
```

---

## Anti-patterns

- **Routing logic inside producers**: each producer deciding which queue to publish to recreates N×M coupling. The bridge must be the single routing authority.
- **Dynamic queue names as strings**: constructing queue names at runtime (`env[`QUEUE_${type}`]`) loses type safety and is hard to audit. Use a typed map as shown above.
- **Side-effects in routing rules**: routing rules should be pure predicates. Avoid DB reads, external fetches, or state mutations inside `match()`.
- **No unmatched-event policy**: silently dropping events with no matching rule means data loss. Always route unknowns to DLQ.
- **Synchronous fan-out without `Promise.all`**: sending to four target queues sequentially wastes latency. Fan out in parallel.

---

## Gotchas

- The bridge Worker acks the inbound message **before** the fan-out `sendBatch` calls complete. If you need at-least-once delivery to targets, ack only after all sends succeed (but this risks double-acking on retry). Prefer `ackAll()` after `await Promise.all(sends)`.
- Each `sendBatch` to a target queue counts as a subrequest. 250 inbound messages routing to 4 queues = 4 subrequest calls (batched), well within limits.
- Routing rules are evaluated in order. If multiple rules match and produce overlapping targets, deduplication is mandatory to avoid duplicate delivery.
- Queue message size is capped at 128 KB. Large payloads must be stored in R2 with a key reference in the envelope.

---

## Verification

```bash
# Publish a test event to the inbound queue
wrangler queues send events-inbound '{"id":"test-1","type":"payment.failed","version":"1.0","source":"payment-svc","timestamp":"2026-08-23T00:00:00Z","payload":{"amount":50000}}'

# Confirm it arrived in both target queues
wrangler queues describe events-payments
wrangler queues describe events-orders   # cross-cutting rule
```

```typescript
// Unit test for rule engine
import { resolveTargets } from './rules';

const paymentFailedEvent = {
  id: 'x', type: 'payment.failed' as const,
  version: '1.0', source: 'test',
  timestamp: new Date().toISOString(),
  payload: { amount: 99 },
};

const targets = resolveTargets(paymentFailedEvent);
assert(targets.includes('QUEUE_PAYMENTS'));
assert(targets.includes('QUEUE_ORDERS')); // cross-cutting rule
```

---

## Related

- `event-driven-fanout-patterns.md`
- `command-pattern-workers-queues-async-processing.md`
- `dead-letter-queue-architecture.md`
- `choreography-vs-orchestration-distributed-workflows.md`
- `workers-queue-fanout-architecture.md`

---

## Sources

- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Message Router (Enterprise Integration Patterns) — Hohpe & Woolf, Addison-Wesley 2003
- AWS EventBridge content-based routing concepts — https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns.html
