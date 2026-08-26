# Domain Events with Cloudflare Queues for Event Sourcing

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Business operations — placing an order, processing a payment, dispatching a shipment — are handled by separate Workers. There is no durable record of what happened or in what order. Debugging requires correlating logs across multiple systems. Replaying history to rebuild state after a bug is impossible.

## Context

Event sourcing stores state as an immutable, append-only sequence of domain events. Instead of updating rows in place, each state change is recorded as a new event. Current state is derived by replaying the event stream from the beginning (or from a snapshot).

Cloudflare Queues deliver messages reliably between Workers, making them a natural event bus. D1 serves as the event store. Events are published to a Queue, consumed by downstream Workers, and written to D1 using `INSERT OR IGNORE ON CONFLICT(event_id)` to guarantee idempotent processing.

## Event Schema and Domain Event Types

```typescript
// events.ts
export interface DomainEvent<T = unknown> {
  eventId: string;        // UUID, globally unique
  aggregateId: string;    // e.g., orderId
  aggregateType: string;  // e.g., 'Order'
  eventType: string;      // e.g., 'OrderPlaced'
  payload: T;
  occurredAt: string;     // ISO-8601
  schemaVersion: number;  // increment on breaking payload changes
}

export interface OrderPlacedPayload {
  orderId: string;
  customerId: string;
  items: { sku: string; qty: number; unitCents: number }[];
  totalCents: number;
}

export interface PaymentProcessedPayload {
  orderId: string;
  chargeId: string;
  amountCents: number;
  processorRef: string;
}

export interface ShipmentDispatchedPayload {
  orderId: string;
  shipmentId: string;
  carrier: string;
  trackingNumber: string;
  estimatedDelivery: string;
}

export type OrderEvent =
  | DomainEvent<OrderPlacedPayload>
  | DomainEvent<PaymentProcessedPayload>
  | DomainEvent<ShipmentDispatchedPayload>;
```

## Publishing Events from a Worker

```typescript
// order-worker.ts
import type { DomainEvent, OrderPlacedPayload } from './events';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'POST' && new URL(request.url).pathname === '/orders') {
      const body = await request.json<Omit<OrderPlacedPayload, 'orderId'>>();
      const orderId = crypto.randomUUID();

      const event: DomainEvent<OrderPlacedPayload> = {
        eventId: crypto.randomUUID(),
        aggregateId: orderId,
        aggregateType: 'Order',
        eventType: 'OrderPlaced',
        payload: { orderId, ...body },
        occurredAt: new Date().toISOString(),
        schemaVersion: 1,
      };

      // Persist to event store first — outbox pattern
      await env.DB.prepare(
        `INSERT INTO events
         (event_id, aggregate_id, aggregate_type, event_type, payload, occurred_at, schema_version)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      )
        .bind(
          event.eventId,
          event.aggregateId,
          event.aggregateType,
          event.eventType,
          JSON.stringify(event.payload),
          event.occurredAt,
          event.schemaVersion
        )
        .run();

      // Publish to queue
      await env.ORDER_EVENTS_QUEUE.send(event);

      return Response.json({ orderId, eventId: event.eventId }, { status: 201 });
    }
    return new Response('not found', { status: 404 });
  },
};
```

## Consumer: Idempotent Event Processing

```typescript
// event-consumer.ts
import type { DomainEvent, OrderPlacedPayload, PaymentProcessedPayload, ShipmentDispatchedPayload } from './events';

export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const ev = msg.body;
      try {
        await processEvent(ev, env);
        msg.ack();
      } catch (err) {
        console.error(`failed to process event ${ev.eventId}`, err);
        msg.retry({ delaySeconds: 10 });
      }
    }
  },
};

async function processEvent(ev: DomainEvent, env: Env): Promise<void> {
  // Idempotency guard — ignore already-processed events
  const existing = await env.DB.prepare(
    `SELECT 1 FROM processed_events WHERE event_id = ?`
  ).bind(ev.eventId).first();
  if (existing) return;

  switch (ev.eventType) {
    case 'OrderPlaced': {
      const p = ev.payload as OrderPlacedPayload;
      await env.DB.prepare(
        `INSERT OR IGNORE INTO order_aggregate
         (order_id, customer_id, status, total_cents, version)
         VALUES (?, ?, 'placed', ?, 1)
         ON CONFLICT(order_id) DO NOTHING`
      ).bind(p.orderId, p.customerId, p.totalCents).run();
      break;
    }
    case 'PaymentProcessed': {
      const p = ev.payload as PaymentProcessedPayload;
      await env.DB.prepare(
        `UPDATE order_aggregate SET status = 'paid', charge_id = ?, version = version + 1
         WHERE order_id = ?`
      ).bind(p.chargeId, p.orderId).run();
      break;
    }
    case 'ShipmentDispatched': {
      const p = ev.payload as ShipmentDispatchedPayload;
      await env.DB.prepare(
        `UPDATE order_aggregate
         SET status = 'shipped', tracking_number = ?, estimated_delivery = ?, version = version + 1
         WHERE order_id = ?`
      ).bind(p.trackingNumber, p.estimatedDelivery, p.orderId).run();
      break;
    }
    default:
      console.warn(`unknown event type: ${ev.eventType}`);
  }

  // Mark processed — idempotent insert
  await env.DB.prepare(
    `INSERT OR IGNORE INTO processed_events (event_id, processed_at) VALUES (?, ?)`
  ).bind(ev.eventId, new Date().toISOString()).run();
}
```

## Rebuilding Aggregate State from the Event Stream

```typescript
// replay.ts
import type { DomainEvent } from './events';

export interface OrderState {
  orderId: string;
  customerId: string;
  status: string;
  totalCents: number;
  chargeId?: string;
  trackingNumber?: string;
  version: number;
}

export async function replayOrder(orderId: string, env: Env): Promise<OrderState | null> {
  const rows = await env.DB.prepare(
    `SELECT event_type, payload FROM events
     WHERE aggregate_id = ? ORDER BY occurred_at ASC`
  ).bind(orderId).all<{ event_type: string; payload: string }>();

  if (!rows.results.length) return null;

  let state: OrderState = {
    orderId,
    customerId: '',
    status: 'unknown',
    totalCents: 0,
    version: 0,
  };

  for (const row of rows.results) {
    const payload = JSON.parse(row.payload);
    state = applyEvent(state, row.event_type, payload);
    state.version += 1;
  }

  return state;
}

function applyEvent(state: OrderState, eventType: string, payload: Record<string, unknown>): OrderState {
  switch (eventType) {
    case 'OrderPlaced':
      return { ...state, customerId: payload.customerId as string, status: 'placed', totalCents: payload.totalCents as number };
    case 'PaymentProcessed':
      return { ...state, status: 'paid', chargeId: payload.chargeId as string };
    case 'ShipmentDispatched':
      return { ...state, status: 'shipped', trackingNumber: payload.trackingNumber as string };
    default:
      return state;
  }
}
```

## D1 Event Store Schema

```sql
CREATE TABLE IF NOT EXISTS events (
  event_id        TEXT PRIMARY KEY,
  aggregate_id    TEXT NOT NULL,
  aggregate_type  TEXT NOT NULL,
  event_type      TEXT NOT NULL,
  payload         TEXT NOT NULL,
  occurred_at     TEXT NOT NULL,
  schema_version  INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_events_agg ON events(aggregate_id, occurred_at);

CREATE TABLE IF NOT EXISTS processed_events (
  event_id     TEXT PRIMARY KEY,
  processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_aggregate (
  order_id          TEXT PRIMARY KEY,
  customer_id       TEXT NOT NULL,
  status            TEXT NOT NULL,
  total_cents       INTEGER NOT NULL,
  charge_id         TEXT,
  tracking_number   TEXT,
  estimated_delivery TEXT,
  version           INTEGER NOT NULL DEFAULT 1
);
```

## Anti-patterns

- **Mutating events** — events are immutable facts about the past. If a payload structure needs to change, increment `schemaVersion` and write a migration Consumer that upcasts old events before applying them.
- **Using Queue delivery as the only durability mechanism** — always write to the `events` table before publishing to the Queue. If the Queue publish fails or the Consumer crashes before `msg.ack()`, the event is re-delivered and idempotent processing handles the duplicate.
- **Querying the aggregate table for replay** — the aggregate table is a cache. Replay always reads from the `events` table.
- **Missing `processed_events` guard** — Queues guarantee at-least-once delivery. Without the idempotency check, a re-delivered event will apply its state change twice.

## Gotchas

- D1 `INSERT OR IGNORE` silently does nothing on conflict. Verify the row was inserted by checking `meta.changes` in the D1 result.
- Queue messages have a maximum body size of 128 KB. For large payloads (e.g., file upload events), store the payload in R2 and include only the R2 key in the event.
- `schema_version` must be included in every event from day one. Adding it later requires a backfill migration across potentially millions of rows.

## Verification

```bash
# Place an order
curl -X POST https://<worker>.workers.dev/orders \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"c1","items":[{"sku":"A","qty":1,"unitCents":999}],"totalCents":999}'

# Check the event store
npx wrangler d1 execute <DB_NAME> \
  --command "SELECT event_id, event_type, occurred_at FROM events ORDER BY occurred_at DESC LIMIT 5"

# Check idempotency: re-send the same eventId (simulate Queue re-delivery)
npx wrangler d1 execute <DB_NAME> \
  --command "SELECT COUNT(*) FROM processed_events WHERE event_id='<eventId>'"
# Should be 1 regardless of how many times the event was delivered
```

## Related

- `cqrs-workers-d1-read-write-separation.md`
- `saga-pattern-workers-durable-objects-compensation.md`

## Sources

- Martin Fowler, *Event Sourcing* — https://martinfowler.com/eaaDev/EventSourcing.html
- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
