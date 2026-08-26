# CQRS (Command Query Responsibility Segregation) with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A single D1 table serves both writes and complex analytics reads. Write-heavy endpoints block read-heavy dashboards; your query model is a compromise that serves neither well. You need to optimise reads and writes independently without splitting into separate services.

## Context

CQRS splits the application model into two explicit sides:

- **Write side (Commands)** — mutates state, enforces invariants, produces events.
- **Read side (Queries)** — returns projections optimised for consumption, never mutates.

In a Workers + D1 topology the write side commits to a normalised schema; a Queue consumer syncs committed events into a denormalised read model (a separate D1 table or a KV projection). Both sides are served by the same Worker via path-based routing.

## Solution

### 1. Types

```typescript
// src/cqrs/types.ts

// --- Commands ---
export interface CreateOrderCommand {
  type: 'CreateOrder';
  orderId: string;
  customerId: string;
  items: Array<{ productId: string; qty: number; unitPrice: number }>;
}

export interface CancelOrderCommand {
  type: 'CancelOrder';
  orderId: string;
  reason: string;
}

export type Command = CreateOrderCommand | CancelOrderCommand;

// --- Queries ---
export interface GetOrderByIdQuery {
  type: 'GetOrderById';
  orderId: string;
}

export interface ListOrdersByCustomerQuery {
  type: 'ListOrdersByCustomer';
  customerId: string;
  limit: number;
  cursor?: string;
}

export type Query = GetOrderByIdQuery | ListOrdersByCustomerQuery;

// --- Domain Events (result of command execution) ---
export interface OrderCreatedEvent {
  type: 'OrderCreated';
  orderId: string;
  customerId: string;
  totalAmount: number;
  items: CreateOrderCommand['items'];
  occurredAt: number;
}

export interface OrderCancelledEvent {
  type: 'OrderCancelled';
  orderId: string;
  reason: string;
  occurredAt: number;
}

export type DomainEvent = OrderCreatedEvent | OrderCancelledEvent;
```

### 2. Write-side command handlers

```typescript
// src/cqrs/command-handlers.ts
import type { Command, DomainEvent, CreateOrderCommand, CancelOrderCommand } from './types';

export interface CommandDeps {
  db: D1Database;
  eventQueue: Queue<DomainEvent>;
}

async function handleCreateOrder(
  cmd: CreateOrderCommand,
  deps: CommandDeps,
): Promise<void> {
  const totalAmount = cmd.items.reduce((s, i) => s + i.qty * i.unitPrice, 0);

  // Transactional write: insert order + line items atomically
  await deps.db.batch([
    deps.db
      .prepare(
        `INSERT INTO orders (id, customer_id, status, total_amount, created_at)
         VALUES (?, ?, 'pending', ?, ?)`,
      )
      .bind(cmd.orderId, cmd.customerId, totalAmount, Date.now()),
    ...cmd.items.map(item =>
      deps.db
        .prepare(
          `INSERT INTO order_items (order_id, product_id, qty, unit_price)
           VALUES (?, ?, ?, ?)`,
        )
        .bind(cmd.orderId, item.productId, item.qty, item.unitPrice),
    ),
  ]);

  // Emit event for read-model projection
  const event: DomainEvent = {
    type: 'OrderCreated',
    orderId: cmd.orderId,
    customerId: cmd.customerId,
    totalAmount,
    items: cmd.items,
    occurredAt: Date.now(),
  };
  await deps.eventQueue.send(event);
}

async function handleCancelOrder(
  cmd: CancelOrderCommand,
  deps: CommandDeps,
): Promise<void> {
  const result = await deps.db
    .prepare(`UPDATE orders SET status = 'cancelled', cancel_reason = ? WHERE id = ? AND status != 'cancelled'`)
    .bind(cmd.reason, cmd.orderId)
    .run();

  if (result.meta.changes === 0) {
    throw new Error(`Order ${cmd.orderId} not found or already cancelled`);
  }

  await deps.eventQueue.send({
    type: 'OrderCancelled',
    orderId: cmd.orderId,
    reason: cmd.reason,
    occurredAt: Date.now(),
  });
}

export async function handleCommand(cmd: Command, deps: CommandDeps): Promise<void> {
  switch (cmd.type) {
    case 'CreateOrder':  return handleCreateOrder(cmd, deps);
    case 'CancelOrder':  return handleCancelOrder(cmd, deps);
    default: {
      const _exhaustive: never = cmd;
      throw new Error(`Unknown command: ${(_exhaustive as any).type}`);
    }
  }
}
```

### 3. Read-side query handlers (denormalised read model)

```typescript
// src/cqrs/query-handlers.ts
import type { Query } from './types';

export interface QueryDeps {
  db: D1Database;
  cache: KVNamespace;
}

// Read-model table: orders_view (denormalised, pre-joined)
interface OrderView {
  orderId: string;
  customerId: string;
  status: string;
  totalAmount: number;
  itemCount: number;
  createdAt: number;
  cancelReason: string | null;
}

async function queryGetOrderById(
  orderId: string,
  deps: QueryDeps,
): Promise<OrderView | null> {
  // Check KV read-cache first (TTL 60 s)
  const cacheKey = `order_view:${orderId}`;
  const cached = await deps.cache.get<OrderView>(cacheKey, 'json');
  if (cached) return cached;

  const row = await deps.db
    .prepare(
      `SELECT order_id, customer_id, status, total_amount, item_count, created_at, cancel_reason
       FROM orders_view WHERE order_id = ?`,
    )
    .bind(orderId)
    .first<{
      order_id: string;
      customer_id: string;
      status: string;
      total_amount: number;
      item_count: number;
      created_at: number;
      cancel_reason: string | null;
    }>();

  if (!row) return null;

  const view: OrderView = {
    orderId: row.order_id,
    customerId: row.customer_id,
    status: row.status,
    totalAmount: row.total_amount,
    itemCount: row.item_count,
    createdAt: row.created_at,
    cancelReason: row.cancel_reason,
  };

  await deps.cache.put(cacheKey, JSON.stringify(view), { expirationTtl: 60 });
  return view;
}

async function queryListOrdersByCustomer(
  customerId: string,
  limit: number,
  cursor: string | undefined,
  deps: QueryDeps,
): Promise<{ orders: OrderView[]; nextCursor: string | null }> {
  const cursorTs = cursor ? parseInt(cursor, 10) : Date.now() + 1;

  const rows = await deps.db
    .prepare(
      `SELECT order_id, customer_id, status, total_amount, item_count, created_at, cancel_reason
       FROM orders_view
       WHERE customer_id = ? AND created_at < ?
       ORDER BY created_at DESC
       LIMIT ?`,
    )
    .bind(customerId, cursorTs, limit + 1)
    .all<{ order_id: string; customer_id: string; status: string; total_amount: number; item_count: number; created_at: number; cancel_reason: string | null }>();

  const items = rows.results.slice(0, limit).map(r => ({
    orderId: r.order_id,
    customerId: r.customer_id,
    status: r.status,
    totalAmount: r.total_amount,
    itemCount: r.item_count,
    createdAt: r.created_at,
    cancelReason: r.cancel_reason,
  }));

  const nextCursor =
    rows.results.length > limit ? String(items[items.length - 1].createdAt) : null;

  return { orders: items, nextCursor };
}

export async function handleQuery(query: Query, deps: QueryDeps): Promise<unknown> {
  switch (query.type) {
    case 'GetOrderById':
      return queryGetOrderById(query.orderId, deps);
    case 'ListOrdersByCustomer':
      return queryListOrdersByCustomer(query.customerId, query.limit, query.cursor, deps);
    default: {
      const _exhaustive: never = query;
      throw new Error(`Unknown query type`);
    }
  }
}
```

### 4. Read-model projection consumer (Queue)

```typescript
// src/cqrs/projection-consumer.ts
import type { DomainEvent } from './types';

export async function projectEvent(event: DomainEvent, db: D1Database): Promise<void> {
  switch (event.type) {
    case 'OrderCreated': {
      await db
        .prepare(
          `INSERT OR IGNORE INTO orders_view
             (order_id, customer_id, status, total_amount, item_count, created_at)
           VALUES (?, ?, 'pending', ?, ?, ?)`,
        )
        .bind(
          event.orderId,
          event.customerId,
          event.totalAmount,
          event.items.reduce((s, i) => s + i.qty, 0),
          event.occurredAt,
        )
        .run();
      break;
    }
    case 'OrderCancelled': {
      await db
        .prepare(
          `UPDATE orders_view SET status = 'cancelled', cancel_reason = ? WHERE order_id = ?`,
        )
        .bind(event.reason, event.orderId)
        .run();
      break;
    }
  }
}

export interface Env {
  DB: D1Database;
}

// Queue consumer entry point
export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await projectEvent(msg.body, env.DB);
        msg.ack();
      } catch (err) {
        console.error('Projection failed', msg.body, err);
        msg.retry();
      }
    }
  },
};
```

### 5. HTTP router composing both sides

```typescript
// src/worker.ts
import { handleCommand } from './cqrs/command-handlers';
import { handleQuery } from './cqrs/query-handlers';
import type { DomainEvent } from './cqrs/types';

export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  EVENTS: Queue<DomainEvent>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url  = new URL(request.url);
    const path = url.pathname;

    // --- Write side ---
    if (request.method === 'POST' && path === '/commands') {
      const cmd = await request.json();
      try {
        await handleCommand(cmd as any, { db: env.DB, eventQueue: env.EVENTS });
        return new Response(null, { status: 202 });
      } catch (err: any) {
        return Response.json({ error: err.message }, { status: 422 });
      }
    }

    // --- Read side ---
    if (request.method === 'GET' && path.startsWith('/queries/orders/')) {
      const orderId = path.split('/')[3];
      const result = await handleQuery(
        { type: 'GetOrderById', orderId },
        { db: env.DB, cache: env.CACHE },
      );
      if (!result) return new Response('Not Found', { status: 404 });
      return Response.json(result);
    }

    if (request.method === 'GET' && path === '/queries/customers/orders') {
      const customerId = url.searchParams.get('customerId') ?? '';
      const limit = parseInt(url.searchParams.get('limit') ?? '20', 10);
      const cursor = url.searchParams.get('cursor') ?? undefined;
      const result = await handleQuery(
        { type: 'ListOrdersByCustomer', customerId, limit, cursor },
        { db: env.DB, cache: env.CACHE },
      );
      return Response.json(result);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

- **Eventual consistency window**: the Queue delay between `OrderCreated` event emission and the projection update is typically < 1 second in Cloudflare Queues with default settings. If the client immediately GETs after a POST, they may see stale data; add `Retry-After: 1` or return a `202 Accepted` with a polling URL.
- **Read-model schema**: `orders_view` is a materialised, denormalised table. Its shape is driven by query patterns, not normalisation rules.
- **Idempotency**: `INSERT OR IGNORE` in the projection consumer prevents duplicate rows if a message is delivered twice.
- **Read model rebuild**: truncate `orders_view` and re-replay all events from the write-side `orders` table to rebuild projections after schema changes.

```sql
-- Write-side schema
CREATE TABLE orders (
  id           TEXT PRIMARY KEY,
  customer_id  TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending',
  total_amount REAL NOT NULL,
  cancel_reason TEXT,
  created_at   INTEGER NOT NULL
);

CREATE TABLE order_items (
  order_id   TEXT NOT NULL REFERENCES orders(id),
  product_id TEXT NOT NULL,
  qty        INTEGER NOT NULL,
  unit_price REAL NOT NULL
);

-- Read-side schema (denormalised view table)
CREATE TABLE orders_view (
  order_id     TEXT PRIMARY KEY,
  customer_id  TEXT NOT NULL,
  status       TEXT NOT NULL,
  total_amount REAL NOT NULL,
  item_count   INTEGER NOT NULL,
  created_at   INTEGER NOT NULL,
  cancel_reason TEXT,
  INDEX idx_orders_view_customer (customer_id, created_at DESC)
);
```

## Anti-patterns

- **Querying the write-side tables from read handlers** — the write schema is normalised for integrity, not read performance. Always query the read model.
- **Synchronous projection** — projecting inside the command handler couples write and read latency. Always use an async Queue.
- **Commands returning domain data** — commands signal `202 Accepted`, never return entity state. The client polls the read model.
- **Sharing the same D1 database object for reads and writes in tests** — use separate in-memory stores to verify the sides are genuinely decoupled.

## Gotchas

- D1 `batch()` is atomic per batch but there is no cross-batch transaction. Design commands to fit within a single batch.
- Queues have an at-least-once delivery guarantee. All projection handlers must be idempotent.
- KV cache TTL must be shorter than the maximum acceptable staleness for your SLA.

## Verification

```bash
# Post a command
curl -X POST http://localhost:8787/commands \
  -H 'Content-Type: application/json' \
  -d '{"type":"CreateOrder","orderId":"o1","customerId":"c1","items":[{"productId":"p1","qty":2,"unitPrice":9.99}]}'

# Query the read model (allow ~1 s for projection)
sleep 1
curl http://localhost:8787/queries/orders/o1
```

## Related

- `workers-hexagonal-architecture-ports-adapters.md`
- `workers-event-driven-webhooks-queues.md`

## Sources

- Martin Fowler, "CQRS" — https://martinfowler.com/bliki/CQRS.html
- Greg Young, CQRS Documents (2010)
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
