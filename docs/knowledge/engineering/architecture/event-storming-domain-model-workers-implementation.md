# Event Storming Domain Model → Workers Implementation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You ran an event storming workshop and produced a big-picture map of domain events,
commands, aggregates, policies, and bounded contexts on sticky notes. Now you need to
translate that artefact into running Cloudflare Workers code without losing the
vocabulary or the boundaries the domain experts gave you.

## Context

Event storming produces five artefact types that map cleanly onto Workers primitives:

| Storming artefact | Workers primitive |
|---|---|
| Domain event (orange) | Queue message / KV event log entry |
| Command (blue) | Worker HTTP handler or RPC method |
| Aggregate (yellow) | Durable Object |
| Policy / reaction (purple) | Queue consumer Worker |
| Read model (green) | D1 projection table / KV cache |

The mapping is mechanical once you internalize it. The goal is zero vocabulary drift
between the sticky-note names and the TypeScript identifiers.

## Translating Commands to Worker Handlers

Each blue sticky becomes a typed command object and an HTTP POST handler.

```typescript
// commands/place-order.ts
export interface PlaceOrderCommand {
  readonly type: 'PlaceOrder';
  readonly customerId: string;
  readonly items: Array<{ skuId: string; qty: number }>;
  readonly idempotencyKey: string;
}

// handlers/place-order.ts
export async function handlePlaceOrder(
  cmd: PlaceOrderCommand,
  env: Env,
): Promise<Response> {
  const id = env.ORDER.idFromName(cmd.idempotencyKey);
  const stub = env.ORDER.get(id);
  const result = await stub.placeOrder(cmd);
  return Response.json(result, { status: 201 });
}
```

## Aggregates as Durable Objects

Each yellow sticky (aggregate) becomes a Durable Object class. State is derived from
an internal event log persisted in DO storage — the same pattern event sourcing
demands.

```typescript
// aggregates/order.ts
export class Order extends DurableObject {
  private events: DomainEvent[] = [];

  async placeOrder(cmd: PlaceOrderCommand): Promise<OrderPlacedEvent> {
    if (this.events.length > 0) throw new Error('Order already exists');

    const event: OrderPlacedEvent = {
      type: 'OrderPlaced',
      orderId: this.ctx.id.toString(),
      customerId: cmd.customerId,
      items: cmd.items,
      occurredAt: new Date().toISOString(),
    };

    this.events.push(event);
    await this.ctx.storage.put('events', this.events);
    await this.publishEvent(event);
    return event;
  }

  private async publishEvent(event: DomainEvent): Promise<void> {
    // env injected via constructor binding
    await (this as any).env.DOMAIN_EVENTS.send(event);
  }
}
```

## Policies as Queue Consumers

Purple stickies ("when X happens, do Y") become Queue consumer Workers. The policy
name becomes the Worker export name.

```typescript
// policies/notify-warehouse-on-order-placed.ts
// Storming sticky: "When OrderPlaced → notify warehouse"
export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      if (msg.body.type !== 'OrderPlaced') { msg.ack(); continue; }

      const event = msg.body as OrderPlacedEvent;
      await env.WAREHOUSE_SERVICE.fetch(new Request(
        'https://warehouse/pick-list',
        { method: 'POST', body: JSON.stringify(event) },
      ));
      msg.ack();
    }
  },
};
```

## Read Models as D1 Projections

Green stickies become D1 tables populated by projection workers that listen to the
same queue with a separate consumer group.

```typescript
// projections/order-summary.ts
export async function projectOrderPlaced(
  event: OrderPlacedEvent,
  env: Env,
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO order_summary (order_id, customer_id, item_count, placed_at)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(order_id) DO NOTHING`,
  )
    .bind(
      event.orderId,
      event.customerId,
      event.items.length,
      event.occurredAt,
    )
    .run();
}
```

## Bounded Context Routing

Events that cross bounded context boundaries travel through a routing worker that
acts as a message bus, preserving context isolation.

```typescript
// router/domain-event-router.ts
const CONTEXT_QUEUE_MAP: Record<string, string> = {
  'OrderPlaced': 'WAREHOUSE_QUEUE',
  'OrderPlaced': 'BILLING_QUEUE',     // fan-out: send to both
  'PaymentConfirmed': 'FULFILLMENT_QUEUE',
};

export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const targets = ROUTING_TABLE[msg.body.type] ?? [];
      await Promise.all(
        targets.map(q => (env as any)[q].send(msg.body)),
      );
      msg.ack();
    }
  },
};

const ROUTING_TABLE: Record<string, string[]> = {
  'OrderPlaced': ['WAREHOUSE_QUEUE', 'BILLING_QUEUE'],
  'PaymentConfirmed': ['FULFILLMENT_QUEUE'],
};
```

## Anti-patterns

- **Renaming storming vocabulary in code** — "OrderCreated" in stickies but
  `CreateOrderEvent` in TypeScript breaks the ubiquitous language. Use the exact
  storming name as the `type` discriminant.
- **Aggregates calling other aggregates directly** — Durable Object stubs must not
  call sibling stubs synchronously; emit an event and let a policy react.
- **Mixing read and write concerns in one Durable Object** — the DO owns write-side
  state; read models live in D1/KV and are updated by projections.
- **Skipping the routing worker** — having every policy subscribe to every queue
  creates implicit coupling between bounded contexts.

## Gotchas

- Queue consumer Workers share a single consumer group per binding; to fan-out one
  event to multiple bounded contexts use separate Queue bindings or a router worker.
- Durable Object IDs derived from `idFromName` are deterministic — use the
  aggregate's natural key (e.g., order ID) so commands are routed to the correct
  instance.
- D1 projections are eventually consistent with the command side; build UIs that
  tolerate a short lag or use optimistic client-side updates.
- Queue `send()` from inside a Durable Object alarm runs in a fresh I/O context;
  always `await` it before the alarm handler returns.

## Verification

```bash
# Confirm event type names match storming vocabulary exactly
grep -r '"type":' src/events/ | sort

# Confirm each policy file name mirrors the storming sticky label
ls src/policies/

# Smoke-test the routing table covers all emitted event types
npx ts-node scripts/verify-routing-coverage.ts
```

## Related

- `domain-events.md`
- `event-sourcing-d1-append-only-store.md`
- `cqrs-cloudflare-workers-d1.md`
- `outbox-pattern-workers-queues-reliable-events.md`
- `bounded-context-design.md`
- `choreography-vs-orchestration-distributed-workflows.md`

## Sources

- Alberto Brandolini, *Introducing Event Storming* (Leanpub, 2021)
- Cloudflare Durable Objects docs — https://developers.cloudflare.com/durable-objects/
- Cloudflare Queues fan-out — https://developers.cloudflare.com/queues/
- Vaughn Vernon, *Implementing Domain-Driven Design*, ch. 7 (Domain Events)
