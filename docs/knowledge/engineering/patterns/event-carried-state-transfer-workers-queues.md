# Event-Carried State Transfer with Cloudflare Workers and Queues

2026-08-24 / example.com / production

---

## Symptom / Use-case

A downstream Worker or Durable Object needs to react to business events but must also know the full state of the entity at the time of the event. Without embedding that state in the message, the consumer is forced to re-query the origin database over a service binding, creating tight coupling and a new source of latency. This pattern eliminates that round-trip by carrying the complete (or projected) entity snapshot inside the queue message itself.

Typical indicators you need this pattern:
- Consumers issue an immediate `fetch()` back to the producer right after receiving a message.
- Consumer logic breaks when the origin record is mutated before the consumer processes the event.
- Integration tests require the producer service to be running alongside the consumer service.

---

## Context

Event-carried state transfer (ECST) is a messaging pattern where each event message contains not just an identifier but the full state of the domain object at the time the event was raised. The consumer can act entirely from the message payload without consulting any external service.

On the Cloudflare Workers stack, D1 is the source of truth, Queues delivers the events, and consumer Workers act on the embedded snapshot. Cloudflare Queues imposes a maximum message body size of 128 KB. For entities larger than that, pair this pattern with the Claim Check pattern: store the snapshot in R2 and embed only the reference in the message.

---

## Code sections

### 1. Domain types shared between producer and consumer

```typescript
// types/events.ts

export type OrderStatus = 'pending' | 'confirmed' | 'shipped' | 'cancelled';

export interface OrderItem {
  productId: string;
  sku: string;
  quantity: number;
  unitPriceCents: number;
}

export interface OrderSnapshot {
  id: string;
  tenantId: string;
  customerId: string;
  status: OrderStatus;
  items: OrderItem[];
  totalCents: number;
  createdAt: string;
  updatedAt: string;
}

export type OrderEventType = 'order.created' | 'order.confirmed' | 'order.shipped' | 'order.cancelled';

export interface OrderEvent {
  eventId: string;
  eventType: OrderEventType;
  occurredAt: string;
  producerVersion: string;
  payload: OrderSnapshot;
}
```

### 2. Producer – building and enqueuing the event

```typescript
// workers/order-producer/src/index.ts
import type { OrderEvent, OrderSnapshot } from '../../types/events';

interface Env {
  DB: D1Database;
  ORDER_EVENTS: Queue<OrderEvent>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { orderId } = await request.json<{ orderId: string }>();
    const [order, items] = await env.DB.batch([
      env.DB.prepare('SELECT * FROM orders WHERE id = ?').bind(orderId),
      env.DB.prepare('SELECT * FROM order_items WHERE order_id = ?').bind(orderId),
    ]);

    const orderRow = order.results[0] as Record<string, unknown>;
    if (!orderRow) return new Response('Not Found', { status: 404 });

    const snapshot: OrderSnapshot = {
      id: orderRow.id as string,
      tenantId: orderRow.tenant_id as string,
      customerId: orderRow.customer_id as string,
      status: orderRow.status as OrderSnapshot['status'],
      items: (items.results as Record<string, unknown>[]).map((r) => ({
        productId: r.product_id as string,
        sku: r.sku as string,
        quantity: r.quantity as number,
        unitPriceCents: r.unit_price_cents as number,
      })),
      totalCents: orderRow.total_cents as number,
      createdAt: orderRow.created_at as string,
      updatedAt: orderRow.updated_at as string,
    };

    const event: OrderEvent = {
      eventId: crypto.randomUUID(),
      eventType: 'order.confirmed',
      occurredAt: new Date().toISOString(),
      producerVersion: '1.4.2',
      payload: snapshot,
    };

    await env.ORDER_EVENTS.send(event);
    return new Response(JSON.stringify({ eventId: event.eventId }), {
      status: 202, headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

### 3. Consumer – acting on the embedded snapshot without re-querying

```typescript
// workers/fulfillment-consumer/src/index.ts
import type { OrderEvent } from '../../types/events';

interface Env {
  DB: D1Database;
}

export default {
  async queue(batch: MessageBatch<OrderEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await handleEvent(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('fulfillment processing failed', { eventId: msg.body.eventId, error: String(err) });
        msg.retry();
      }
    }
  },
};

async function handleEvent(event: OrderEvent, env: Env): Promise<void> {
  if (event.eventType !== 'order.confirmed') return;
  const { payload: order } = event;

  await env.DB.prepare(
    `INSERT INTO fulfillment_tasks
       (event_id, order_id, tenant_id, customer_id, total_cents, status, received_at)
     VALUES (?, ?, ?, ?, ?, 'pending', ?)
     ON CONFLICT (event_id) DO NOTHING`
  ).bind(event.eventId, order.id, order.tenantId, order.customerId, order.totalCents, new Date().toISOString()).run();

  for (const item of order.items) {
    await env.DB.prepare(
      `INSERT INTO fulfillment_items (event_id, product_id, sku, quantity) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING`
    ).bind(event.eventId, item.productId, item.sku, item.quantity).run();
  }
}
```

### 4. Schema versioning – tolerant reader on the consumer side

```typescript
// workers/fulfillment-consumer/src/versioning.ts
import type { OrderEvent, OrderSnapshot } from '../../types/events';

export function normalizeOrderEvent(raw: unknown): OrderEvent {
  const event = raw as Partial<OrderEvent>;
  if (!event.eventId || !event.eventType || !event.payload) {
    throw new Error('Invalid event envelope: missing required fields');
  }
  const payload = event.payload as Partial<OrderSnapshot>;
  return {
    eventId: event.eventId,
    eventType: event.eventType,
    occurredAt: event.occurredAt ?? new Date().toISOString(),
    producerVersion: event.producerVersion ?? '0.0.0',
    payload: {
      id: payload.id!,
      tenantId: payload.tenantId ?? 'unknown',
      customerId: payload.customerId!,
      status: payload.status ?? 'pending',
      items: payload.items ?? [],
      totalCents: payload.totalCents ?? 0,
      createdAt: payload.createdAt ?? new Date().toISOString(),
      updatedAt: payload.updatedAt ?? new Date().toISOString(),
    },
  };
}
```

### 5. wrangler.toml – queue binding for producer and consumer

```toml
# Producer wrangler.toml
name = "order-producer"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[queues.producers]]
queue = "order-events"
binding = "ORDER_EVENTS"

[[d1_databases]]
binding = "DB"
database_name = "orders-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

---

## Anti-patterns

- **Embedding only the ID and fetching state from the producer on arrival.** This re-couples producer and consumer at runtime.
- **Mutable snapshots.** Never let a consumer write back to the snapshot or treat the embedded state as a live object.
- **Skipping schema versioning.** If the producer and consumer deploy independently, you will have mismatched schemas in flight.
- **Sending raw DB rows.** Serialize a domain projection, not the internal DB schema.
- **Unbounded payload growth.** Large blobs should use the Claim Check pattern with R2.

---

## Gotchas

- **128 KB queue message limit.** Profile your typical snapshot sizes in staging before going to production.
- **`ON CONFLICT DO NOTHING` is mandatory for idempotent consumers.** The same message can be redelivered after a transient consumer error.
- **Consumer cannot see partial updates.** Build the snapshot after the full transaction commits.

---

## Verification

```typescript
test('fulfillment consumer handles order.confirmed without outbound calls', async () => {
  const event = {
    eventId: 'test-uuid-1234',
    eventType: 'order.confirmed',
    occurredAt: '2026-08-24T10:00:00Z',
    producerVersion: '1.4.2',
    payload: {
      id: 'order-abc', tenantId: 'tenant-1', customerId: 'cust-9', status: 'confirmed',
      items: [{ productId: 'p1', sku: 'SKU-A', quantity: 2, unitPriceCents: 1000 }],
      totalCents: 2000, createdAt: '2026-08-24T09:00:00Z', updatedAt: '2026-08-24T10:00:00Z',
    },
  };
  // No fetch mock needed – consumer reads only from event payload
});
```

---

## Related

- `outbox-pattern-d1-reliable-publishing.md`
- `claim-check-pattern-r2-queues.md`
- `idempotency-key-pattern-workers-d1.md`
- `competing-consumers-workers-queues.md`

---

## Sources

- Cloudflare Queues documentation – https://developers.cloudflare.com/queues/
- Martin Fowler – Event-Carried State Transfer – https://martinfowler.com/articles/201701-event-driven.html
- Cloudflare D1 batched queries – https://developers.cloudflare.com/d1/platform/client-api/#batch-statements
