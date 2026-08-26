# Event-Carried State Transfer on Cloudflare Workers and Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your queue consumers receive thin event messages (containing only an entity ID) and must call back the source service to fetch current state before they can do any useful work. This synchronous callback introduces coupling, increases latency, and creates a cascade failure mode: if the source service is down or rate-limiting, every consumer stalls. You want consumers to work completely independently from the source service at processing time.

## Context

Event-Carried State Transfer (ECST) embeds the full entity snapshot in the queue message itself, so consumers never need a call-back to the producer. The trade-off is larger message payloads (bandwidth for coupling reduction), but on Cloudflare Queues the 128 KB per-message limit is rarely a constraint for typical domain entities. Schema versioning via a `_version` field lets producers evolve the payload without breaking existing consumers. Consumer idempotency is enforced by a D1 `processed_events` table with a `UNIQUE` constraint on `event_id`, preventing duplicate side effects when Queues delivers a message more than once (at-least-once semantics).

## Publishing a Full Entity Snapshot

```typescript
// producer-worker.ts
import { Env } from './types';

// Current payload schema — bump _version on breaking changes
export interface OrderPlacedPayload {
  _version: 2;
  event_id: string;
  event_type: 'order.placed';
  occurred_at: string; // ISO-8601
  order: {
    id: string;
    customerId: string;
    status: 'pending' | 'confirmed' | 'shipped' | 'cancelled';
    lineItems: Array<{ sku: string; qty: number; unitPriceCents: number }>;
    totalCents: number;
    currency: string;
    shippingAddress: {
      line1: string;
      city: string;
      country: string;
      postalCode: string;
    };
  };
  customer: {
    id: string;
    email: string;
    firstName: string;
    tier: 'standard' | 'premium';
  };
}

export async function publishOrderPlaced(
  env: Env,
  order: Order,
  customer: Customer,
): Promise<void> {
  const payload: OrderPlacedPayload = {
    _version: 2,
    event_id: crypto.randomUUID(),
    event_type: 'order.placed',
    occurred_at: new Date().toISOString(),
    order: {
      id:              order.id,
      customerId:      order.customerId,
      status:          order.status,
      lineItems:       order.lineItems,
      totalCents:      order.totalCents,
      currency:        order.currency,
      shippingAddress: order.shippingAddress,
    },
    customer: {
      id:        customer.id,
      email:     customer.email,
      firstName: customer.firstName,
      tier:      customer.tier,
    },
  };

  await env.ORDER_EVENTS.send(payload, { contentType: 'json' });
}
```

## Consumer Idempotency with D1

```typescript
// consumer-worker.ts
import { Env } from './types';
import { OrderPlacedPayload } from './producer-worker';

export default {
  async queue(batch: MessageBatch<OrderPlacedPayload>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      await processMessage(env, msg);
    }
  },
};

async function processMessage(
  env: Env,
  msg: Message<OrderPlacedPayload>,
): Promise<void> {
  const event = msg.body;

  // Guard: insert or skip — UNIQUE(event_id) makes this atomic
  const result = await env.DB.prepare(
    `INSERT INTO processed_events (event_id, event_type, processed_at)
     VALUES (?, ?, unixepoch())
     ON CONFLICT(event_id) DO NOTHING`,
  ).bind(event.event_id, event.event_type).run();

  if (result.meta.changes === 0) {
    // Duplicate delivery — ack silently
    msg.ack();
    return;
  }

  // Route by schema version for backward compatibility
  if (event._version === 2) {
    await handleV2OrderPlaced(env, event);
  } else {
    // Unknown version — nack so Queues retries after a future deploy
    msg.retry();
    return;
  }

  msg.ack();
}

async function handleV2OrderPlaced(
  env: Env,
  event: OrderPlacedPayload,
): Promise<void> {
  // All data is in the payload — no outbound HTTP calls
  await env.DB.prepare(
    `INSERT INTO order_notifications (order_id, customer_email, total_cents, currency, sent_at)
     VALUES (?, ?, ?, ?, unixepoch())
     ON CONFLICT(order_id) DO NOTHING`,
  ).bind(
    event.order.id,
    event.customer.email,
    event.order.totalCents,
    event.order.currency,
  ).run();
}
```

## Schema Evolution: Backward-Compatible Additions

When adding a new field to an existing payload version, make it optional and provide a default in the consumer so both old and new messages process correctly without a `_version` bump.

```typescript
// v2 payload extended with optional field — no version bump needed
interface OrderPlacedPayloadV2Extended extends OrderPlacedPayload {
  order: OrderPlacedPayload['order'] & {
    promoCode?: string;  // optional addition — safe for existing consumers
  };
}

// Consumer reads new field with fallback
const promoCode = (event as OrderPlacedPayloadV2Extended).order.promoCode ?? null;

// Breaking change (rename, removal, type change) REQUIRES a _version bump to 3
// and a parallel consumer branch:
// if (event._version === 3) { handleV3(...); }
// if (event._version === 2) { handleV2(...); }
```

## ECST Trade-offs

| Concern | ECST approach |
|---|---|
| Payload size | Full entity snapshot; stays well under 128 KB Queues limit for typical domains |
| Stale data risk | Snapshot reflects state at publish time; not suitable for real-time inventory or pricing |
| Coupling | Zero runtime coupling to producer; only schema coupling (managed by `_version`) |
| Replay | Re-publishing old snapshots gives consumers a point-in-time view, not current state |

## Anti-patterns

- **Thin events (ID-only)** — forces consumer to call back the producer, re-introducing runtime coupling and cascade failure.
- **Omitting `_version`** — any payload change is then a silent breaking change; always version the schema from the first publish.
- **Mutable fields in the snapshot** — embed the state exactly as it was at the time of the event; never post-process or enrich the snapshot before publishing.
- **Sharing internal DB types as the payload schema** — the payload is a public contract; define it independently of your ORM or D1 row types.

## Gotchas

- Cloudflare Queues guarantees at-least-once delivery; always implement idempotency on the consumer side.
- The 128 KB per-message limit applies to the serialized JSON body; large arrays of line items can approach this limit for high-volume orders.
- `msg.retry()` requeues the message immediately unless the batch's `retryAll()` is called, which also retries successfully processed messages; prefer per-message `retry()`.
- D1 `ON CONFLICT DO NOTHING` does not throw; check `result.meta.changes` to distinguish insert from skip.
- Schema version routing (`_version` check) must be exhaustive; log and dead-letter unknown versions rather than silently dropping them.

## Verification

```bash
# Create processed_events table
wrangler d1 execute example project-db \
  --command="CREATE TABLE IF NOT EXISTS processed_events (event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, processed_at INTEGER NOT NULL)" \
  --env production

# Check for duplicate processing (count should equal unique event_ids)
wrangler d1 execute example project-db \
  --command="SELECT event_type, COUNT(*) as total FROM processed_events GROUP BY event_type" \
  --env production

# Simulate a publish (local dev)
wrangler dev
curl -X POST http://localhost:8787/orders \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"cust_1","items":[{"sku":"SKU-A","qty":2,"unitPriceCents":999}]}'
```

## Related

- `outbox-pattern-workers-d1-queues-reliable-events.md`
- `read-model-projection-d1-queues-workers.md`
- `anti-corruption-layer-workers-service-boundary.md`

## Sources

- Richardson, Chris — Event-Carried State Transfer pattern — https://microservices.io/patterns/data/event-carried-state-transfer.html
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Cloudflare Queues Message Size Limits — https://developers.cloudflare.com/queues/platform/limits/
