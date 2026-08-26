# Hexagonal (Ports and Adapters) Architecture in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers codebase has domain logic tangled with D1 queries, `fetch()` calls to MailChannels, and direct Queues sends. Unit tests require a deployed D1 database and real network calls, making them slow and brittle. You need a structure where the core domain can be tested in isolation and infrastructure adapters can be swapped without touching business logic.

## Context

Hexagonal Architecture (Ports and Adapters), coined by Alistair Cockburn, separates a system into a domain core and a set of ports (interfaces) through which the core communicates with the outside world. Adapters implement those ports for specific technologies. In Cloudflare Workers the `Env` object becomes the dependency injection container: production adapters receive the real D1 binding, KV namespace, or Queue; test adapters receive in-memory implementations. This pattern makes the domain layer technology-agnostic and independently testable, and it maps cleanly to Workers' single-file entry point and binding system.

## Folder Structure

```
src/
  domain/
    order.ts            # Pure domain entities and business rules
    order-service.ts    # Domain service, depends only on ports
  ports/
    order-repository.ts # StoragePort interface
    email-sender.ts     # EmailPort interface
    event-publisher.ts  # QueuePort interface
  adapters/
    d1-order-repository.ts    # D1 implementation of StoragePort
    mailchannels-sender.ts    # MailChannels implementation of EmailPort
    cloudflare-queue-publisher.ts # Queues implementation of QueuePort
    in-memory-order-repository.ts # Test double
    in-memory-email-sender.ts     # Test double
  index.ts              # Workers entry point — wires adapters to domain
  types.ts              # Env bindings type
```

## Defining Ports (Interfaces)

```typescript
// src/ports/order-repository.ts
export interface Order {
  id: string;
  customerId: string;
  status: 'pending' | 'confirmed' | 'cancelled';
  totalCents: number;
  createdAt: Date;
}

export interface OrderRepository {
  save(order: Order): Promise<void>;
  findById(id: string): Promise<Order | null>;
  findByCustomer(customerId: string, limit: number): Promise<Order[]>;
}

// src/ports/email-sender.ts
export interface EmailMessage {
  to: string;
  subject: string;
  html: string;
}
export interface EmailSender {
  send(msg: EmailMessage): Promise<void>;
}

// src/ports/event-publisher.ts
export interface DomainEvent { event_id: string; event_type: string; payload: unknown; }
export interface EventPublisher {
  publish(event: DomainEvent): Promise<void>;
}
```

## Domain Service (Zero Infrastructure Imports)

```typescript
// src/domain/order-service.ts
import { Order, OrderRepository } from '../ports/order-repository';
import { EmailSender } from '../ports/email-sender';
import { EventPublisher } from '../ports/event-publisher';

export class OrderService {
  constructor(
    private readonly orders: OrderRepository,
    private readonly email: EmailSender,
    private readonly events: EventPublisher,
  ) {}

  async placeOrder(
    customerId: string,
    totalCents: number,
  ): Promise<Order> {
    const order: Order = {
      id:          crypto.randomUUID(),
      customerId,
      status:      'pending',
      totalCents,
      createdAt:   new Date(),
    };

    await this.orders.save(order);

    await this.events.publish({
      event_id:   crypto.randomUUID(),
      event_type: 'order.placed',
      payload:    { orderId: order.id, customerId, totalCents },
    });

    await this.email.send({
      to:      `${customerId}@example.com`,
      subject: 'Order confirmed',
      html:    `<p>Order ${order.id} received.</p>`,
    });

    return order;
  }
}
```

## Concrete Adapters

```typescript
// src/adapters/d1-order-repository.ts
import { Order, OrderRepository } from '../ports/order-repository';
import { D1Database } from '@cloudflare/workers-types';

export class D1OrderRepository implements OrderRepository {
  constructor(private readonly db: D1Database) {}

  async save(order: Order): Promise<void> {
    await this.db.prepare(
      `INSERT INTO orders (id, customer_id, status, total_cents, created_at)
       VALUES (?, ?, ?, ?, unixepoch())
       ON CONFLICT(id) DO UPDATE SET status = excluded.status`,
    ).bind(order.id, order.customerId, order.status, order.totalCents).run();
  }

  async findById(id: string): Promise<Order | null> {
    const row = await this.db.prepare(
      `SELECT id, customer_id, status, total_cents, created_at FROM orders WHERE id = ?`,
    ).bind(id).first<Record<string, unknown>>();
    return row ? rowToOrder(row) : null;
  }

  async findByCustomer(customerId: string, limit: number): Promise<Order[]> {
    const { results } = await this.db.prepare(
      `SELECT id, customer_id, status, total_cents, created_at FROM orders WHERE customer_id = ? LIMIT ?`,
    ).bind(customerId, limit).all<Record<string, unknown>>();
    return results.map(rowToOrder);
  }
}

function rowToOrder(row: Record<string, unknown>): Order {
  return {
    id:          row.id as string,
    customerId:  row.customer_id as string,
    status:      row.status as Order['status'],
    totalCents:  row.total_cents as number,
    createdAt:   new Date((row.created_at as number) * 1000),
  };
}

// src/adapters/cloudflare-queue-publisher.ts
import { DomainEvent, EventPublisher } from '../ports/event-publisher';
export class CloudflareQueuePublisher implements EventPublisher {
  constructor(private readonly queue: Queue) {}
  async publish(event: DomainEvent): Promise<void> {
    await this.queue.send(event, { contentType: 'json' });
  }
}
```

## Dependency Injection via the Env Object

```typescript
// src/index.ts  —  Workers entry point
import { Env } from './types';
import { OrderService } from './domain/order-service';
import { D1OrderRepository } from './adapters/d1-order-repository';
import { MailChannelsSender } from './adapters/mailchannels-sender';
import { CloudflareQueuePublisher } from './adapters/cloudflare-queue-publisher';

function buildOrderService(env: Env): OrderService {
  return new OrderService(
    new D1OrderRepository(env.DB),
    new MailChannelsSender(env),
    new CloudflareQueuePublisher(env.ORDER_QUEUE),
  );
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const svc = buildOrderService(env);
    const { customerId, totalCents } = await req.json<{ customerId: string; totalCents: number }>();
    const order = await svc.placeOrder(customerId, totalCents);
    return Response.json(order);
  },
};
```

## In-Memory Test Doubles

```typescript
// src/adapters/in-memory-order-repository.ts
import { Order, OrderRepository } from '../ports/order-repository';

export class InMemoryOrderRepository implements OrderRepository {
  private store = new Map<string, Order>();

  async save(order: Order): Promise<void> { this.store.set(order.id, { ...order }); }
  async findById(id: string): Promise<Order | null> { return this.store.get(id) ?? null; }
  async findByCustomer(customerId: string, limit: number): Promise<Order[]> {
    return [...this.store.values()].filter(o => o.customerId === customerId).slice(0, limit);
  }
}

// test/order-service.test.ts  —  runs with plain Node.js, no Workers runtime needed
import { OrderService } from '../src/domain/order-service';
import { InMemoryOrderRepository } from '../src/adapters/in-memory-order-repository';

const makeService = () => new OrderService(
  new InMemoryOrderRepository(),
  { send: async () => {} },       // inline stub for EmailSender
  { publish: async () => {} },    // inline stub for EventPublisher
);

test('placeOrder creates a pending order', async () => {
  const svc = makeService();
  const order = await svc.placeOrder('cust_1', 4999);
  expect(order.status).toBe('pending');
  expect(order.totalCents).toBe(4999);
});
```

## Anti-patterns

- **Importing D1 or `fetch` directly in the domain layer** — the domain must depend only on ports, never on concrete infrastructure.
- **Fat entry point (index.ts) with business logic** — the entry point's only job is wiring adapters; domain rules belong in the domain service.
- **One giant `Env`-typed class** — pass the minimal port interface, not the full `Env`, to each adapter constructor.
- **Test doubles that share mutable state between tests** — construct a fresh `InMemoryOrderRepository` in each test case.

## Gotchas

- Cloudflare Workers do not support Node.js `process.env`; all configuration comes through the `Env` binding object passed to the `fetch` handler.
- TypeScript `interface` types are erased at runtime; you cannot use `instanceof` to check which adapter is injected — use a discriminant property if needed.
- The Workers runtime constructs a new global scope per invocation (V8 isolate); do not store mutable request-scoped state in module-level variables.
- `D1Database` bindings are not available in `vitest` without `@cloudflare/vitest-pool-workers`; use in-memory adapters for pure unit tests and the pool for integration tests.

## Verification

```bash
# Run unit tests (no Workers runtime needed)
npx vitest run test/order-service.test.ts

# Run integration tests against local D1
wrangler dev &
curl -X POST http://localhost:8787/orders \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"cust_42","totalCents":2999}'

# Type-check the full project
npx tsc --noEmit
```

## Related

- `anti-corruption-layer-workers-service-boundary.md`
- `outbox-pattern-workers-d1-queues-reliable-events.md`
- `read-model-projection-d1-queues-workers.md`

## Sources

- Cockburn, Alistair — Hexagonal Architecture — https://alistair.cockburn.us/hexagonal-architecture/
- Cloudflare Workers Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/
- Cloudflare Vitest Pool Workers — https://developers.cloudflare.com/workers/testing/vitest-integration/
