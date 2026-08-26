# Domain Event Dispatcher with Cloudflare Queues in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After a domain operation completes (e.g. order placed, user registered) multiple side-effects must
run: send an email, update a search index, notify analytics. Triggering them synchronously inside
the handler couples services, inflates response latency, and breaks when a downstream is slow.

## Context

The Domain Event pattern decouples the originator from consumers. In Cloudflare Workers:

1. Domain services raise typed events during request handling.
2. An `EventDispatcher` accumulates them in-process.
3. After the response is sent, `ctx.waitUntil` flushes events to Cloudflare Queues.
4. A separate Queue consumer Worker processes each event independently.

This keeps the HTTP response fast, events are durable (Queues retry on failure), and
consumers are decoupled behind the queue interface.

---

## Section 1 — Domain Event Base Class and Concrete Events

```typescript
// src/domain/events/DomainEvent.ts

export abstract class DomainEvent {
  readonly occurredAt: string;
  abstract readonly type: string;

  constructor() {
    this.occurredAt = new Date().toISOString();
  }

  toJSON(): Record<string, unknown> {
    return {
      type: this.type,
      occurredAt: this.occurredAt,
      ...this.payload(),
    };
  }

  protected abstract payload(): Record<string, unknown>;
}

// src/domain/events/OrderPlacedEvent.ts

import { DomainEvent } from './DomainEvent';

export class OrderPlacedEvent extends DomainEvent {
  readonly type = 'order.placed';

  constructor(
    public readonly orderId: string,
    public readonly userId: string,
    public readonly totalCents: number
  ) {
    super();
  }

  protected payload(): Record<string, unknown> {
    return {
      orderId: this.orderId,
      userId: this.userId,
      totalCents: this.totalCents,
    };
  }
}

// src/domain/events/UserRegisteredEvent.ts

import { DomainEvent } from './DomainEvent';

export class UserRegisteredEvent extends DomainEvent {
  readonly type = 'user.registered';

  constructor(
    public readonly userId: string,
    public readonly email: string
  ) {
    super();
  }

  protected payload(): Record<string, unknown> {
    return { userId: this.userId, email: this.email };
  }
}
```

---

## Section 2 — In-Process Event Dispatcher

The dispatcher is a per-request accumulator. Domain services call `dispatcher.raise()` during
business logic; the handler flushes via `ctx.waitUntil` after sending the response.

```typescript
// src/infrastructure/events/EventDispatcher.ts

import type { Queue } from '@cloudflare/workers-types';
import type { DomainEvent } from '../../domain/events/DomainEvent';

export class EventDispatcher {
  private readonly events: DomainEvent[] = [];

  /** Called by domain services to register an event for later dispatch. */
  raise(event: DomainEvent): void {
    this.events.push(event);
  }

  /** Returns a snapshot of all raised events (useful in tests). */
  get raised(): ReadonlyArray<DomainEvent> {
    return this.events;
  }

  /**
   * Flush all accumulated events to a Cloudflare Queue.
   * Intended to be passed to ctx.waitUntil so it runs after the response.
   */
  async flush(queue: Queue): Promise<void> {
    if (this.events.length === 0) return;

    const messages = this.events.map((e) => ({
      body: e.toJSON(),
      // contentType defaults to json in Queues v2
    }));

    await queue.sendBatch(messages);
  }
}
```

---

## Section 3 — Handler Wiring with ctx.waitUntil

```typescript
// src/handlers/placeOrderHandler.ts

import type { D1Database, Queue, ExecutionContext } from '@cloudflare/workers-types';
import { EventDispatcher } from '../infrastructure/events/EventDispatcher';
import { UnitOfWork } from '../infrastructure/db/UnitOfWork';
import { OrderRepository } from '../infrastructure/repositories/OrderRepository';
import { InventoryRepository } from '../infrastructure/repositories/InventoryRepository';
import { OrderPlacedEvent } from '../domain/events/OrderPlacedEvent';

interface Env {
  DB: D1Database;
  ORDER_EVENTS_QUEUE: Queue;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const body = await request.json<{
      orderId: string;
      userId: string;
      skuId: string;
      quantity: number;
      totalCents: number;
    }>();

    const dispatcher = new EventDispatcher();

    // --- domain work ---
    const uow = new UnitOfWork(env.DB);
    const orders = new OrderRepository(uow);
    const inventory = new InventoryRepository(uow);

    orders.insertOrder({
      id: body.orderId,
      userId: body.userId,
      totalCents: body.totalCents,
      status: 'pending',
      version: 1,
    });
    inventory.decrementStock(body.skuId, body.quantity);

    await uow.commit(); // atomic D1 batch

    // Raise event only after successful commit
    dispatcher.raise(
      new OrderPlacedEvent(body.orderId, body.userId, body.totalCents)
    );

    // Flush to Queue after response — does not block the HTTP reply
    ctx.waitUntil(dispatcher.flush(env.ORDER_EVENTS_QUEUE));

    return Response.json({ orderId: body.orderId }, { status: 201 });
  },
};
```

---

## Section 4 — Queue Consumer Worker

```typescript
// src/consumers/orderEventsConsumer.ts

import type { Queue, MessageBatch } from '@cloudflare/workers-types';

interface OrderPlacedPayload {
  type: 'order.placed';
  occurredAt: string;
  orderId: string;
  userId: string;
  totalCents: number;
}

type DomainEventPayload = OrderPlacedPayload; // extend as more events are added

interface Env {
  EMAIL_QUEUE: Queue; // downstream queue for email service
}

export default {
  async queue(
    batch: MessageBatch<DomainEventPayload>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await handleEvent(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('Failed to handle event', msg.body, err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function handleEvent(
  event: DomainEventPayload,
  env: Env
): Promise<void> {
  switch (event.type) {
    case 'order.placed':
      // Fan out to email queue, analytics, etc.
      await env.EMAIL_QUEUE.send({
        to: `user-${event.userId}@example.com`,
        subject: `Order ${event.orderId} confirmed`,
        totalCents: event.totalCents,
      });
      break;
    default: {
      const exhaustive: never = event;
      console.warn('Unknown event type', exhaustive);
    }
  }
}
```

---

## Anti-patterns

- **Raising events before committing** — if the D1 batch fails after enqueuing, the event is a lie. Always raise *after* a successful commit.
- **Raising events synchronously inside `ctx.waitUntil`** — domain code should not be aware of `ctx`. Only the handler wires the flush.
- **One huge event with everything** — keep events minimal and named after what *happened*, not what consumers *need*. Consumers fetch additional data if required.
- **Swallowing errors in `flush`** — `ctx.waitUntil` errors are not retried by Workers; if `queue.sendBatch` fails the events are lost. Log or use a dead-letter strategy.

## Gotchas

- `Queue.sendBatch` is limited to 100 messages per call and 256 KB total body size.
- `ctx.waitUntil` extends the Worker lifetime but not indefinitely — the total CPU limit still applies.
- Queue consumers run in a separate Worker invocation; they cannot share in-process state with the producer.
- Queues provide *at-least-once* delivery; consumers must be idempotent (check if the side-effect already happened).

## Verification

```bash
# Check queue binding in wrangler.toml
grep -A3 'ORDER_EVENTS_QUEUE' wrangler.toml

# Test dispatcher accumulation
npx vitest run src/infrastructure/events/EventDispatcher.test.ts

# Smoke-test via Wrangler dev
npx wrangler dev --local
curl -X POST http://localhost:8787/ -H 'Content-Type: application/json' \
  -d '{"orderId":"o1","userId":"u1","skuId":"sku1","quantity":1,"totalCents":999}'
```

## Related

- `workers-unit-of-work-d1-batch.md` — atomic D1 commits that events are raised after
- `workers-repository-pattern-d1.md` — repositories used inside the same handler

## Sources

- [Cloudflare Queues documentation](https://developers.cloudflare.com/queues/)
- Vernon, V. (2013). *Implementing Domain-Driven Design*. Addison-Wesley. Chapter 8: Domain Events.
