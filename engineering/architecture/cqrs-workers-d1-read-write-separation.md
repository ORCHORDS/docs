# CQRS with Workers: Separate Read and Write Paths Using D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A single D1 table is used for both writes and dashboard reads. As write volume grows, read queries slow down because they compete for the same table locks. Indexes added to speed up reads slow down inserts. The read and write patterns are fundamentally different and need independent scaling paths.

## Context

Command Query Responsibility Segregation (CQRS) separates the model you write to from the model you read from. In a Workers environment:

- A **write Worker** accepts commands, validates them, and appends events to an `events` table in D1 (append-only, never updated).
- A **Queue consumer Worker** reads new events and updates a denormalised `read_model` table optimised for query patterns.
- A **read Worker** serves queries exclusively from the `read_model` table.

The event log is the source of truth. The read model is a derived projection that can be rebuilt from scratch at any time.

## Write Worker: Append-Only Event Log

```typescript
// write-worker.ts
import { z } from 'zod';

const PlaceOrderCommand = z.object({
  orderId: z.string().uuid(),
  customerId: z.string().uuid(),
  items: z.array(z.object({ sku: z.string(), qty: z.number().int().positive() })),
  totalCents: z.number().int().positive(),
});

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('method not allowed', { status: 405 });
    }

    const url = new URL(request.url);

    if (url.pathname === '/commands/place-order') {
      const raw = await request.json();
      const parsed = PlaceOrderCommand.safeParse(raw);
      if (!parsed.success) {
        return Response.json({ errors: parsed.error.flatten() }, { status: 422 });
      }

      const cmd = parsed.data;
      const eventId = crypto.randomUUID();
      const occurredAt = new Date().toISOString();

      await env.DB.prepare(
        `INSERT INTO events (event_id, aggregate_id, event_type, payload, occurred_at)
         VALUES (?, ?, ?, ?, ?)`
      )
        .bind(
          eventId,
          cmd.orderId,
          'OrderPlaced',
          JSON.stringify(cmd),
          occurredAt
        )
        .run();

      // Enqueue for projection
      await env.EVENT_QUEUE.send({
        eventId,
        aggregateId: cmd.orderId,
        eventType: 'OrderPlaced',
        payload: cmd,
        occurredAt,
      });

      return Response.json(
        { eventId, status: 'accepted', pollAt: `/read/orders/${cmd.orderId}` },
        { status: 202 }
      );
    }

    return new Response('not found', { status: 404 });
  },
};
```

## Queue Consumer: Projecting Events into the Read Model

```typescript
// projection-consumer.ts
interface DomainEvent {
  eventId: string;
  aggregateId: string;
  eventType: string;
  payload: Record<string, unknown>;
  occurredAt: string;
}

export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const ev = msg.body;
      try {
        await projectEvent(ev, env);
        msg.ack();
      } catch (err) {
        console.error('projection failed', ev.eventId, err);
        msg.retry({ delaySeconds: 5 });
      }
    }
  },
};

async function projectEvent(ev: DomainEvent, env: Env): Promise<void> {
  if (ev.eventType === 'OrderPlaced') {
    const p = ev.payload as {
      orderId: string;
      customerId: string;
      items: { sku: string; qty: number }[];
      totalCents: number;
    };

    await env.DB.prepare(
      `INSERT OR REPLACE INTO read_model_orders
       (order_id, customer_id, status, total_cents, item_count, projected_at)
       VALUES (?, ?, 'placed', ?, ?, ?)`
    )
      .bind(p.orderId, p.customerId, p.totalCents, p.items.length, new Date().toISOString())
      .run();
  }

  if (ev.eventType === 'PaymentProcessed') {
    const p = ev.payload as { orderId: string; chargeId: string };
    await env.DB.prepare(
      `UPDATE read_model_orders SET status = 'paid', charge_id = ?, projected_at = ? WHERE order_id = ?`
    )
      .bind(p.chargeId, new Date().toISOString(), p.orderId)
      .run();
  }
}
```

## Read Worker: Query the Read Model

```typescript
// read-worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const orderMatch = url.pathname.match(/^\/read\/orders\/([\w-]+)$/);

    if (orderMatch) {
      const orderId = orderMatch[1];

      const row = await env.DB.prepare(
        `SELECT order_id, customer_id, status, total_cents, item_count, charge_id, projected_at
         FROM read_model_orders WHERE order_id = ?`
      )
        .bind(orderId)
        .first<{
          order_id: string;
          customer_id: string;
          status: string;
          total_cents: number;
          item_count: number;
          charge_id: string | null;
          projected_at: string;
        }>();

      if (!row) {
        return Response.json({ status: 'pending', message: 'read model not yet projected' }, { status: 202 });
      }

      // Emit sync_lag metric
      const lagMs = await computeSyncLag(orderId, row.projected_at, env);
      env.ANALYTICS.writeDataPoint({
        blobs: ['sync_lag', row.status],
        doubles: [lagMs],
        indexes: ['orders'],
      });

      return Response.json(row);
    }

    return new Response('not found', { status: 404 });
  },
};

async function computeSyncLag(orderId: string, projectedAt: string, env: Env): Promise<number> {
  const eventRow = await env.DB.prepare(
    `SELECT occurred_at FROM events WHERE aggregate_id = ? ORDER BY occurred_at DESC LIMIT 1`
  )
    .bind(orderId)
    .first<{ occurred_at: string }>();

  if (!eventRow) return 0;
  return new Date(projectedAt).getTime() - new Date(eventRow.occurred_at).getTime();
}
```

## D1 Schema

```sql
-- Append-only event store
CREATE TABLE IF NOT EXISTS events (
  event_id     TEXT PRIMARY KEY,
  aggregate_id TEXT NOT NULL,
  event_type   TEXT NOT NULL,
  payload      TEXT NOT NULL,
  occurred_at  TEXT NOT NULL
);
CREATE INDEX idx_events_aggregate ON events(aggregate_id, occurred_at);

-- Denormalised read model
CREATE TABLE IF NOT EXISTS read_model_orders (
  order_id     TEXT PRIMARY KEY,
  customer_id  TEXT NOT NULL,
  status       TEXT NOT NULL,
  total_cents  INTEGER NOT NULL,
  item_count   INTEGER NOT NULL,
  charge_id    TEXT,
  projected_at TEXT NOT NULL
);
CREATE INDEX idx_read_customer ON read_model_orders(customer_id, status);
```

## Anti-patterns

- **Querying `events` directly from the read Worker** — this couples the read path to the event schema and creates the same contention you were trying to avoid. Always project first.
- **Updating events table rows** — the events table must be append-only. Updates destroy the audit trail and break replay.
- **Synchronous projection on the write path** — projecting inside the write Worker couples latency. Use a Queue so the write path returns 202 immediately.
- **Not handling the 202 at read time** — clients must poll the read endpoint and handle a 202 meaning "not yet projected" rather than treating it as an error.

## Gotchas

- D1 Queue consumers run in a separate Worker; they share the same `env.DB` binding but are billed and rate-limited independently.
- `sync_lag` will be negative if the projection worker's clock skew is larger than actual lag. Use the event's `occurred_at` field (written by the write Worker) as the reference point, not wall-clock time in the consumer.
- Rebuilding the read model from scratch requires replaying all events in `occurred_at` order. Add a `sequence_number` column (auto-increment) to `events` to guarantee stable ordering.

## Verification

```bash
# Post a command
curl -X POST https://write.<worker>.workers.dev/commands/place-order \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"550e8400-e29b-41d4-a716-446655440000","customerId":"c1","items":[{"sku":"A","qty":2}],"totalCents":2000}'
# Expected 202: {"eventId":"...","status":"accepted","pollAt":"/read/orders/550e..."}

# Poll the read model (allow ~1s for Queue delivery)
sleep 1
curl https://read.<worker>.workers.dev/read/orders/550e8400-e29b-41d4-a716-446655440000
# Expected: {"order_id":"550e...","status":"placed", ...}

# Check event store
npx wrangler d1 execute <DB_NAME> \
  --command "SELECT event_id, event_type, occurred_at FROM events ORDER BY occurred_at DESC LIMIT 5"
```

## Related

- `domain-events-workers-queues-event-sourcing.md`
- `saga-pattern-workers-durable-objects-compensation.md`

## Sources

- Greg Young, *CQRS Documents* — https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
