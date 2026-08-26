# CQRS with D1 in Cloudflare Workers: Read/Write Separation

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
As a Workers application scales, mixing read and write logic in the same handler creates contention, slows iteration, and makes auditing harder. You need a clean boundary between operations that mutate state and operations that query it, so each can be optimised independently.

---

## Context
Command Query Responsibility Segregation (CQRS) splits the application model into a write side (commands) and a read side (queries). In Cloudflare Workers, D1 is the durable store for both sides — commands write normalised rows and read queries target denormalised indexed views or plain indexed columns. Async projections (materialised-view updates) are offloaded with `ctx.waitUntil` so they never block the HTTP response. A lightweight event stub publishes domain events to a Queue after each successful command, enabling downstream consumers to keep their own read models in sync.

---

## Section 1 — D1 Schema & Wrangler Config

```toml
# wrangler.toml
name = "cqrs-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "cqrs-db"
database_id = "<your-d1-database-id>"

[[queues.producers]]
binding = "EVENT_QUEUE"
queue = "domain-events"
```

```sql
-- migrations/0001_init.sql
CREATE TABLE IF NOT EXISTS orders (
  id          TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',
  total_cents INTEGER NOT NULL,
  created_at  TEXT NOT NULL
);

-- Denormalised read view (kept in sync by projection)
CREATE TABLE IF NOT EXISTS order_summaries (
  id            TEXT PRIMARY KEY,
  customer_name TEXT NOT NULL,
  status        TEXT NOT NULL,
  total_cents   INTEGER NOT NULL,
  created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_summaries_customer
  ON order_summaries (customer_name);
```

---

## Section 2 — CommandBus and QueryBus Implementation

```typescript
// src/cqrs/types.ts
export interface Command<T = unknown> {
  readonly type: string;
  readonly payload: T;
}

export interface Query<T = unknown> {
  readonly type: string;
  readonly params: T;
}

export type CommandHandler<C extends Command> = (
  cmd: C,
  env: Env
) => Promise<void>;

export type QueryHandler<Q extends Query, R> = (
  query: Q,
  env: Env
) => Promise<R>;

// src/cqrs/command-bus.ts
import type { Command, CommandHandler } from './types';

export class CommandBus {
  private handlers = new Map<string, CommandHandler<Command>>();

  register<C extends Command>(type: string, handler: CommandHandler<C>): void {
    this.handlers.set(type, handler as CommandHandler<Command>);
  }

  async dispatch(cmd: Command, env: Env): Promise<void> {
    const handler = this.handlers.get(cmd.type);
    if (!handler) throw new Error(`No handler for command: ${cmd.type}`);
    await handler(cmd, env);
  }
}

// src/cqrs/query-bus.ts
import type { Query, QueryHandler } from './types';

export class QueryBus {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private handlers = new Map<string, QueryHandler<Query, any>>();

  register<Q extends Query, R>(type: string, handler: QueryHandler<Q, R>): void {
    this.handlers.set(type, handler as QueryHandler<Query, unknown>);
  }

  async execute<R>(query: Query, env: Env): Promise<R> {
    const handler = this.handlers.get(query.type);
    if (!handler) throw new Error(`No handler for query: ${query.type}`);
    return handler(query, env) as Promise<R>;
  }
}

// src/commands/create-order.ts
import { randomUUID } from 'crypto';
import type { Command } from '../cqrs/types';

export interface CreateOrderPayload {
  customerId: string;
  lineItems: Array<{ productId: string; quantity: number; priceCents: number }>;
}

export const CREATE_ORDER = 'order/create';

export type CreateOrderCommand = Command<CreateOrderPayload>;

export async function handleCreateOrder(
  cmd: CreateOrderCommand,
  env: Env
): Promise<void> {
  const id = randomUUID();
  const total = cmd.payload.lineItems.reduce(
    (sum, li) => sum + li.priceCents * li.quantity,
    0
  );
  const now = new Date().toISOString();

  // Write side — mutate D1
  await env.DB.prepare(
    'INSERT INTO orders (id, customer_id, status, total_cents, created_at) VALUES (?, ?, ?, ?, ?)'
  )
    .bind(id, cmd.payload.customerId, 'pending', total, now)
    .run();

  // Publish domain event to Queue (event sourcing stub)
  await env.EVENT_QUEUE.send({
    schemaVersion: 1,
    type: 'OrderCreated',
    aggregateId: id,
    payload: { customerId: cmd.payload.customerId, totalCents: total },
    occurredAt: now,
  });
}

// src/queries/list-orders.ts
import type { Query } from '../cqrs/types';

export interface ListOrdersParams {
  customerName?: string;
  limit: number;
  offset: number;
}

export interface OrderSummary {
  id: string;
  customerName: string;
  status: string;
  totalCents: number;
  createdAt: string;
}

export const LIST_ORDERS = 'order/list';
export type ListOrdersQuery = Query<ListOrdersParams>;

export async function handleListOrders(
  query: ListOrdersQuery,
  env: Env
): Promise<OrderSummary[]> {
  const { customerName, limit, offset } = query.params;

  // Read side — query denormalised view via index
  if (customerName) {
    const result = await env.DB.prepare(
      'SELECT * FROM order_summaries WHERE customer_name = ? LIMIT ? OFFSET ?'
    )
      .bind(customerName, limit, offset)
      .all<OrderSummary>();
    return result.results;
  }

  const result = await env.DB.prepare(
    'SELECT * FROM order_summaries LIMIT ? OFFSET ?'
  )
    .bind(limit, offset)
    .all<OrderSummary>();
  return result.results;
}
```

---

## Section 3 — Worker Entry & Async Projection

```typescript
// src/projections/order-summary.ts
// Runs inside ctx.waitUntil — never blocks the response
export async function projectOrderCreated(
  event: { aggregateId: string; payload: { customerId: string; totalCents: number }; occurredAt: string },
  env: Env
): Promise<void> {
  // In a real system, fetch customer name from KV or another D1 table
  const customerName = `Customer-${event.payload.customerId.slice(0, 8)}`;

  await env.DB.prepare(
    `INSERT INTO order_summaries (id, customer_name, status, total_cents, created_at)
     VALUES (?, ?, 'pending', ?, ?)
     ON CONFLICT(id) DO NOTHING`
  )
    .bind(event.aggregateId, customerName, event.payload.totalCents, event.occurredAt)
    .run();
}

// src/index.ts
import { CommandBus } from './cqrs/command-bus';
import { QueryBus } from './cqrs/query-bus';
import { CREATE_ORDER, handleCreateOrder } from './commands/create-order';
import { LIST_ORDERS, handleListOrders } from './queries/list-orders';
import { projectOrderCreated } from './projections/order-summary';

const commandBus = new CommandBus();
commandBus.register(CREATE_ORDER, handleCreateOrder);

const queryBus = new QueryBus();
queryBus.register(LIST_ORDERS, handleListOrders);

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/orders') {
      const body = await request.json<{ customerId: string; lineItems: unknown[] }>();
      const cmd = { type: CREATE_ORDER, payload: body };
      await commandBus.dispatch(cmd, env);

      // Async projection — does not delay the 201 response
      ctx.waitUntil(
        projectOrderCreated(
          { aggregateId: 'projected-stub', payload: { customerId: body.customerId, totalCents: 0 }, occurredAt: new Date().toISOString() },
          env
        )
      );

      return new Response(null, { status: 201 });
    }

    if (request.method === 'GET' && url.pathname === '/orders') {
      const params = Object.fromEntries(url.searchParams);
      const query = {
        type: LIST_ORDERS,
        params: {
          customerName: params.customerName,
          limit: Number(params.limit ?? 20),
          offset: Number(params.offset ?? 0),
        },
      };
      const orders = await queryBus.execute(query, env);
      return Response.json(orders);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Anti-patterns
- **Querying the write table directly from the read path** — bypasses indexing on `order_summaries` and couples the two models together.
- **Synchronous projections inside the command handler** — blocks the response; always use `ctx.waitUntil` or an async Queue consumer.
- **A single god-handler that checks `request.method`** — defeats the purpose of CQRS; route at the bus level, not inside handlers.

---

## Gotchas
- D1 `prepare().run()` is fire-and-forget for writes; check `meta.changes` to confirm a row was actually inserted.
- `ctx.waitUntil` promises do not throw to the caller — wrap the projection in a try/catch and log failures to Logpush.
- Queue `send()` is best-effort; design projections to be idempotent using `ON CONFLICT DO NOTHING`.

---

## Verification

```bash
# Apply migration
wrangler d1 execute cqrs-db --file=migrations/0001_init.sql

# Create an order
curl -X POST https://<worker>.workers.dev/orders \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"cust-1","lineItems":[{"productId":"p1","quantity":2,"priceCents":500}]}'

# Read orders
curl 'https://<worker>.workers.dev/orders?limit=10&offset=0'

# Inspect D1 directly
wrangler d1 execute cqrs-db --command='SELECT * FROM orders LIMIT 5'
```

---

## Related
- `workers-hexagonal-ports-adapters.md`
- `workers-event-driven-fanout-queues.md`
- `workers-clean-architecture-use-cases.md`

---

## Sources
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Martin Fowler — CQRS — https://martinfowler.com/bliki/CQRS.html
