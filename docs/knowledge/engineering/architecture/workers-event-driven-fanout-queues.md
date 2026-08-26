# Event-Driven Fan-out Architecture with Workers Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
A single Workers handler that calls payment, notification, and analytics logic in sequence blocks the response, couples domains, and breaks partially when one downstream fails. You need to publish a domain event once and let independent consumers react asynchronously without a shared codebase.

---

## Context
Workers Queues provides a durable, at-least-once message bus. The fan-out pattern uses a primary Queue as the event backbone: the publishing Worker enqueues a single enriched event, and a dispatcher Worker re-enqueues the same message into per-domain sub-queues (payments, notifications, analytics). Each sub-queue has its own consumer Worker so domains scale and deploy independently. A dead-letter queue captures events that exhaust retries. All events carry a `schemaVersion` field so consumers can handle shape changes without a coordinated deployment.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml  (dispatcher worker)
name = "event-dispatcher"
main = "src/dispatcher.ts"
compatibility_date = "2025-01-01"

[[queues.consumers]]
queue = "domain-events"
max_batch_size = 50
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "domain-events-dlq"

[[queues.producers]]
binding = "PAYMENTS_QUEUE"
queue = "payments-events"

[[queues.producers]]
binding = "NOTIFICATIONS_QUEUE"
queue = "notifications-events"

[[queues.producers]]
binding = "ANALYTICS_QUEUE"
queue = "analytics-events"
```

```toml
# wrangler.toml  (publishing worker, e.g. the Orders API)
[[queues.producers]]
binding = "EVENT_QUEUE"
queue = "domain-events"
```

---

## Section 2 — EventBus, Dispatcher, and Sub-queue Consumers

```typescript
// src/event-bus.ts  (used by publishing workers)
export interface DomainEvent<T = unknown> {
  schemaVersion: number;    // bump when payload shape changes
  type: string;             // e.g. 'OrderPlaced', 'PaymentFailed'
  aggregateId: string;
  occurredAt: string;       // ISO-8601
  payload: T;
}

export class EventBus {
  constructor(private readonly queue: Queue<DomainEvent>) {}

  async publish(event: DomainEvent): Promise<void> {
    await this.queue.send(event, { contentType: 'json' });
  }

  async publishBatch(events: DomainEvent[]): Promise<void> {
    await this.queue.sendBatch(
      events.map((e) => ({ body: e, contentType: 'json' }))
    );
  }
}

// src/dispatcher.ts  (fan-out consumer)
import type { DomainEvent } from './event-bus';

// Which event types each domain cares about
const ROUTING: Record<string, Array<keyof Env>> = {
  OrderPlaced:    ['PAYMENTS_QUEUE', 'NOTIFICATIONS_QUEUE', 'ANALYTICS_QUEUE'],
  PaymentFailed:  ['NOTIFICATIONS_QUEUE', 'ANALYTICS_QUEUE'],
  PaymentSuccess: ['NOTIFICATIONS_QUEUE', 'ANALYTICS_QUEUE'],
  UserRegistered: ['NOTIFICATIONS_QUEUE', 'ANALYTICS_QUEUE'],
};

export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    const fanouts: Array<Promise<void>> = [];

    for (const msg of batch.messages) {
      const event = msg.body;
      const destinations = ROUTING[event.type] ?? [];

      for (const binding of destinations) {
        const q = env[binding] as Queue<DomainEvent>;
        fanouts.push(
          q.send(event, { contentType: 'json' }).then(() => msg.ack())
        );
      }

      // Acknowledge immediately if no routing — prevents infinite retry
      if (destinations.length === 0) msg.ack();
    }

    await Promise.all(fanouts);
  },
};

// src/consumers/payments-consumer.ts
import type { DomainEvent } from '../event-bus';

interface OrderPlacedPayload {
  customerId: string;
  totalCents: number;
  currency: string;
}

export default {
  async queue(batch: MessageBatch<DomainEvent<OrderPlacedPayload>>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body;

      // Schema version guard — handle old and new shapes
      if (event.schemaVersion !== 1) {
        console.warn(`Unsupported schema version ${event.schemaVersion} for ${event.type}`);
        msg.ack(); // do not retry unknown versions
        continue;
      }

      try {
        await processPayment(event.payload, env);
        msg.ack();
      } catch (err) {
        console.error('Payment processing failed', err);
        msg.retry(); // will go to DLQ after max_retries exhausted
      }
    }
  },
};

async function processPayment(
  payload: OrderPlacedPayload,
  _env: Env
): Promise<void> {
  // Placeholder: call payment gateway SDK here
  console.log(`Charging ${payload.totalCents} ${payload.currency} for ${payload.customerId}`);
}

// src/consumers/notifications-consumer.ts
import type { DomainEvent } from '../event-bus';

export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await sendNotification(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('Notification failed', err);
        msg.retry();
      }
    }
  },
};

async function sendNotification(event: DomainEvent, _env: Env): Promise<void> {
  console.log(`Sending notification for ${event.type} on aggregate ${event.aggregateId}`);
}

// src/consumers/dlq-consumer.ts  (dead-letter queue consumer)
import type { DomainEvent } from '../event-bus';

export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      // Persist failed events to D1 for manual replay
      await env.DB.prepare(
        'INSERT INTO failed_events (id, type, payload, failed_at) VALUES (?, ?, ?, ?)'
      )
        .bind(
          msg.body.aggregateId,
          msg.body.type,
          JSON.stringify(msg.body.payload),
          new Date().toISOString()
        )
        .run();

      msg.ack(); // always ack from DLQ to prevent infinite loop
    }
  },
};
```

---

## Section 3 — Publishing from an API Worker & Integration Test

```typescript
// src/orders-api.ts  (publishing worker)
import { EventBus } from './event-bus';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/orders') {
      return new Response('Not found', { status: 404 });
    }

    const body = await request.json<{ customerId: string; totalCents: number; currency: string }>();
    const bus = new EventBus(env.EVENT_QUEUE);

    await bus.publish({
      schemaVersion: 1,
      type: 'OrderPlaced',
      aggregateId: crypto.randomUUID(),
      occurredAt: new Date().toISOString(),
      payload: body,
    });

    return new Response(null, { status: 202 });
  },
};
```

```bash
# integration-test.sh — manual smoke test via wrangler dev

# Terminal 1: start all workers locally
wrangler dev --config wrangler.orders-api.toml &
wrangler dev --config wrangler.dispatcher.toml &
wrangler dev --config wrangler.payments-consumer.toml &

# Terminal 2: publish an event
curl -X POST http://localhost:8787/orders \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"cust-42","totalCents":4999,"currency":"USD"}'

# Expect HTTP 202 immediately; check consumer logs for 'Charging 4999 USD'
```

---

## Anti-patterns
- **One mega-consumer handling all event types** — couples all domains into a single deploy; a bug in analytics brings down payments.
- **Not setting `dead_letter_queue`** — failed events silently vanish after retries; always configure a DLQ.
- **Mutable event payloads without `schemaVersion`** — a payload shape change breaks consumers that deployed first; always version.

---

## Gotchas
- Queue delivery is at-least-once; make every consumer idempotent (use `aggregateId` as an upsert key in D1).
- `msg.retry()` counts against `max_retries`; calling it in a loop within the same batch execution wastes retries — fail fast and return.
- Fan-out multiplies message volume: 1 event × 3 destinations × 3 retries = up to 9 Queue operations per failure.

---

## Verification

```bash
# List queues
wrangler queues list

# Inspect DLQ message count
wrangler queues consumer list domain-events-dlq

# Check failed_events table
wrangler d1 execute <db-name> --command='SELECT * FROM failed_events ORDER BY failed_at DESC LIMIT 10'

# Tail consumer logs in prod
wrangler tail event-dispatcher
wrangler tail payments-consumer
```

---

## Related
- `workers-cqrs-d1-read-write-separation.md`
- `workers-actor-model-durable-objects.md`

---

## Sources
- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Cloudflare Queues dead-letter queues — https://developers.cloudflare.com/queues/reference/dead-letter-queues/
- Enterprise Integration Patterns — https://www.enterpriseintegrationpatterns.com/patterns/messaging/PublishSubscribeChannel.html
