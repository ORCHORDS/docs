# Actor Model Implementation with Durable Objects in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need fine-grained, isolated, stateful concurrency in a serverless environment. Multiple requests race to update shared state, causing conflicts, lost updates, or complex locking schemes. Typical scenarios: real-time collaboration rooms, per-user session management, per-entity rate limiters, game lobbies, order state machines.

## Context

Cloudflare Workers are stateless by design. Coordinating mutable state across multiple Workers instances requires an external store and careful locking. Durable Objects (DOs) solve this by providing a single-threaded execution context with co-located storage — exactly the properties the Actor Model requires. Each DO is an actor: it owns its state, processes messages one at a time, and communicates only through message passing (HTTP fetch).

The Actor Model, formalised by Hewitt (1973), defines actors as the universal primitive of concurrent computation. An actor:
- Has a unique address.
- Maintains private state.
- Processes one message at a time from its mailbox.
- Responds by sending messages, creating new actors, or changing behaviour.

Durable Objects map directly to this model.

## Solution

### 1. Define an Actor (Durable Object)

```typescript
// actors/OrderActor.ts
import { DurableObjectState, DurableObjectNamespace } from '@cloudflare/workers-types';

export interface OrderState {
  id: string;
  status: 'pending' | 'confirmed' | 'shipped' | 'cancelled';
  items: { sku: string; qty: number }[];
  updatedAt: number;
}

export interface ActorEnv {
  INVENTORY_ACTOR: DurableObjectNamespace;
  NOTIFICATION_ACTOR: DurableObjectNamespace;
}

export class OrderActor {
  private state: DurableObjectState;
  private env: ActorEnv;
  private order: OrderState | null = null;

  constructor(state: DurableObjectState, env: ActorEnv) {
    this.state = state;
    this.env = env;
  }

  // --- message dispatch ---
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const msg = url.pathname.slice(1); // e.g. "confirm", "ship", "cancel"

    await this.hydrate();

    switch (msg) {
      case 'confirm': return this.handleConfirm(request);
      case 'ship':    return this.handleShip(request);
      case 'cancel':  return this.handleCancel(request);
      case 'status':  return this.handleStatus();
      default:
        return new Response('Unknown message', { status: 400 });
    }
  }

  // --- private state ---
  private async hydrate(): Promise<void> {
    if (!this.order) {
      this.order = await this.state.storage.get<OrderState>('order') ?? null;
    }
  }

  private async persist(): Promise<void> {
    await this.state.storage.put('order', this.order!);
  }

  // --- message handlers (one at a time — DO serialises these) ---
  private async handleConfirm(request: Request): Promise<Response> {
    const body = await request.json<{ items: OrderState['items'] }>();

    if (this.order?.status === 'confirmed') {
      return Response.json({ error: 'Already confirmed' }, { status: 409 });
    }

    // Send message to InventoryActor before confirming
    const invId = this.env.INVENTORY_ACTOR.idFromName('global');
    const invStub = this.env.INVENTORY_ACTOR.get(invId);
    const invRes = await invStub.fetch('https://actor/reserve', {
      method: 'POST',
      body: JSON.stringify({ items: body.items }),
    });

    if (!invRes.ok) {
      return Response.json({ error: 'Inventory reservation failed' }, { status: 422 });
    }

    this.order = {
      id: this.state.id.toString(),
      status: 'confirmed',
      items: body.items,
      updatedAt: Date.now(),
    };

    await this.persist();

    // Fire-and-forget notification actor
    const notifId = this.env.NOTIFICATION_ACTOR.idFromName('email');
    const notifStub = this.env.NOTIFICATION_ACTOR.get(notifId);
    notifStub.fetch('https://actor/send', {
      method: 'POST',
      body: JSON.stringify({ event: 'order.confirmed', orderId: this.order.id }),
    }).catch(() => { /* best-effort */ });

    return Response.json({ ok: true, order: this.order });
  }

  private async handleShip(_req: Request): Promise<Response> {
    if (this.order?.status !== 'confirmed') {
      return Response.json({ error: 'Cannot ship' }, { status: 409 });
    }
    this.order.status = 'shipped';
    this.order.updatedAt = Date.now();
    await this.persist();
    return Response.json({ ok: true, order: this.order });
  }

  private async handleCancel(_req: Request): Promise<Response> {
    if (!this.order || this.order.status === 'shipped') {
      return Response.json({ error: 'Cannot cancel' }, { status: 409 });
    }
    this.order.status = 'cancelled';
    this.order.updatedAt = Date.now();
    await this.persist();
    return Response.json({ ok: true, order: this.order });
  }

  private handleStatus(): Response {
    return Response.json(this.order ?? { error: 'Not found' }, {
      status: this.order ? 200 : 404,
    });
  }
}
```

### 2. Actor Address — obtaining a stub by ID or name

```typescript
// Stable actor identity via deterministic name
function orderActorStub(env: ActorEnv & { ORDER_ACTOR: DurableObjectNamespace }, orderId: string) {
  const id = env.ORDER_ACTOR.idFromName(`order:${orderId}`);
  return env.ORDER_ACTOR.get(id);
}

// Random actor (for anonymous sessions)
function newSessionActor(env: { SESSION_ACTOR: DurableObjectNamespace }) {
  const id = env.SESSION_ACTOR.newUniqueId();
  return { stub: env.SESSION_ACTOR.get(id), id: id.toString() };
}
```

### 3. Bounded Mailbox with Alarm-Based Backpressure

DOs process one request at a time but queue incoming ones internally. For actors that can be overwhelmed, implement a bounded mailbox using DO Alarms and a KV-backed queue counter.

```typescript
export class ThrottledActor {
  private state: DurableObjectState;
  private readonly MAX_QUEUE = 50;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const inFlight = (await this.state.storage.get<number>('inFlight')) ?? 0;

    if (inFlight >= this.MAX_QUEUE) {
      // Mailbox full — apply backpressure
      return new Response('Mailbox full', { status: 429 });
    }

    await this.state.storage.put('inFlight', inFlight + 1);

    try {
      const result = await this.processMessage(request);
      return result;
    } finally {
      const current = (await this.state.storage.get<number>('inFlight')) ?? 1;
      await this.state.storage.put('inFlight', Math.max(0, current - 1));
    }
  }

  async alarm(): Promise<void> {
    // Alarm fires to drain any stuck state after a crash
    await this.state.storage.put('inFlight', 0);
  }

  private async processMessage(_req: Request): Promise<Response> {
    // Set a safety alarm in case we crash mid-processing
    await this.state.storage.setAlarm(Date.now() + 30_000);
    // ... actual work ...
    await this.state.storage.deleteAlarm();
    return Response.json({ ok: true });
  }
}
```

### 4. Actor Supervision and Restart

DOs automatically restart on crash (the runtime recreates the object from stored state). Implement explicit supervision for application-level errors:

```typescript
export class SupervisedActor {
  private state: DurableObjectState;
  private readonly MAX_FAILURES = 3;
  private readonly BACKOFF_MS = [1000, 5000, 30_000];

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const failures = (await this.state.storage.get<number>('failureCount')) ?? 0;

    if (failures >= this.MAX_FAILURES) {
      const lastFail = (await this.state.storage.get<number>('lastFailureAt')) ?? 0;
      const backoff = this.BACKOFF_MS[Math.min(failures - 1, this.BACKOFF_MS.length - 1)];
      if (Date.now() - lastFail < backoff) {
        return new Response('Actor in backoff', { status: 503 });
      }
      // Backoff expired — allow retry
    }

    try {
      const result = await this.handleMessage(request);
      // Reset failure count on success
      await this.state.storage.put('failureCount', 0);
      return result;
    } catch (err) {
      const newCount = failures + 1;
      await this.state.storage.put('failureCount', newCount);
      await this.state.storage.put('lastFailureAt', Date.now());
      console.error(`Actor failure #${newCount}:`, err);
      return new Response('Actor error', { status: 500 });
    }
  }

  private async handleMessage(_req: Request): Promise<Response> {
    return Response.json({ ok: true });
  }
}
```

### 5. Gateway Worker (routing messages to actors)

```typescript
// worker.ts
import { OrderActor } from './actors/OrderActor';
export { OrderActor };

interface Env {
  ORDER_ACTOR: DurableObjectNamespace;
  INVENTORY_ACTOR: DurableObjectNamespace;
  NOTIFICATION_ACTOR: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // /orders/:id/:message
    const match = url.pathname.match(/^\/orders\/([^/]+)\/([^/]+)$/);
    if (!match) return new Response('Not found', { status: 404 });

    const [, orderId, message] = match;
    const actorId = env.ORDER_ACTOR.idFromName(`order:${orderId}`);
    const stub = env.ORDER_ACTOR.get(actorId);

    // Forward to actor — change URL path to just the message name
    const actorUrl = new URL(request.url);
    actorUrl.pathname = `/${message}`;
    return stub.fetch(new Request(actorUrl, request));
  },
};
```

## Implementation Details

- **Single-threaded guarantee**: The DO runtime serialises all `fetch()` calls to the same DO instance. No mutex required.
- **Co-located storage**: `state.storage` reads/writes are atomic with respect to the actor's execution context.
- **Actor address stability**: `idFromName()` produces the same DO every time for the same string — use namespaced keys (`order:${uuid}`) to avoid cross-entity collisions.
- **Cross-actor messaging**: Use `stub.fetch()` from inside a DO handler. The call is a real HTTP request routed through Cloudflare's network; keep it within the same datacenter via `locationHint` if latency matters.
- **Alarm as heartbeat**: Use `state.storage.setAlarm()` for periodic maintenance (expiry, cleanup, retry) without external cron.

## Anti-patterns

- **Shared mutable KV as actor state**: KV is eventually consistent and lacks transactional semantics. Use DO storage for actor-owned state.
- **Calling multiple actors in a chain and expecting atomicity**: Each actor is independent. Use sagas or compensating transactions for distributed consistency.
- **God actor**: A single DO handling all entity types becomes a bottleneck. One actor class per aggregate type.
- **Synchronous fan-out inside a handler**: Awaiting many actor stubs sequentially in one handler creates long response chains. Use `Promise.all()` or fire-and-forget where order does not matter.

## Gotchas

- A DO instance can only run in one Cloudflare location at a time. Cross-region latency is real if the creator and the DO are on opposite sides of the planet.
- `state.storage` operations inside a DO are synchronous from the actor's perspective but still async JS. Always `await` them.
- DO IDs created with `newUniqueId()` are not reconstructable from application data — persist them if you need to look up the actor later.
- The DO request limit is 1000 requests/second per DO. Very hot actors (e.g., a global counter) will saturate this; shard them.
- Alarms are best-effort: they fire at least once but may fire more than once. Make alarm handlers idempotent.

## Verification

```bash
# Local dev — wrangler starts multiple DO instances
npx wrangler dev

# Send a confirm message to actor order:abc-123
curl -X POST http://localhost:8787/orders/abc-123/confirm \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"sku":"SKU-1","qty":2}]}'

# Check status
curl http://localhost:8787/orders/abc-123/status

# Verify single-threaded execution: fire 10 concurrent updates
for i in $(seq 1 10); do
  curl -s -X POST http://localhost:8787/orders/abc-123/ship &
done
wait
# Only one should succeed (status: confirmed -> shipped), others return 409
```

## Related

- `workers-cqrs-command-query-separation.md`
- `domain-event-dispatcher-queues.md`
- `unit-of-work-d1-batch.md`
- `workers-multi-tenant-isolation-durable-objects.md`

## Sources

- Hewitt, Bishop, Steiger (1973). "A Universal Modular ACTOR Formalism for Artificial Intelligence".
- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- Cloudflare DO Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare DO Storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
