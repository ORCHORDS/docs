# Clean Architecture Use Cases in TypeScript Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Business logic mixed directly into Workers `fetch` handlers becomes impossible to test in isolation and breaks every time an HTTP detail changes. You need a layer that encodes business rules as pure TypeScript, decoupled from any framework, HTTP library, or Cloudflare binding.

---

## Context
Clean Architecture places use cases at the centre of the application. Each use case class has a single `execute(input)` method that returns a typed `Result<T, E>` rather than throwing, keeping control flow explicit. Repository interfaces are injected via the constructor so the use case never imports infrastructure. The Workers `fetch` handler is a thin adapter that translates the HTTP request into a use case input DTO, calls `execute`, and maps the result to an HTTP response. Tests run in plain Node/Vitest with an in-memory repository — no Workers runtime required.

---

## Section 1 — Domain Types & Result Type

```typescript
// src/domain/result.ts
export type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

export const ok = <T>(value: T): Result<T, never> => ({ ok: true, value });
export const err = <E>(error: E): Result<never, E> => ({ ok: false, error });

// src/domain/order.ts
export interface OrderLine {
  productId: string;
  quantity: number;
  priceCents: number;
}

export interface Order {
  id: string;
  customerId: string;
  lines: OrderLine[];
  totalCents: number;
  status: 'pending' | 'confirmed' | 'cancelled';
  createdAt: string;
}

// src/domain/errors.ts
export class CustomerNotFoundError extends Error {
  readonly type = 'CustomerNotFound' as const;
  constructor(customerId: string) {
    super(`Customer not found: ${customerId}`);
  }
}

export class EmptyOrderError extends Error {
  readonly type = 'EmptyOrder' as const;
  constructor() { super('An order must have at least one line item'); }
}

export class InsufficientStockError extends Error {
  readonly type = 'InsufficientStock' as const;
  constructor(public readonly productId: string) {
    super(`Insufficient stock for product: ${productId}`);
  }
}

export type CreateOrderError =
  | CustomerNotFoundError
  | EmptyOrderError
  | InsufficientStockError;
```

---

## Section 2 — Repository Interface & Use Case

```typescript
// src/ports/order-repository.ts
import type { Order } from '../domain/order';

export interface OrderRepository {
  save(order: Order): Promise<void>;
  findById(id: string): Promise<Order | null>;
  findByCustomer(customerId: string, limit: number): Promise<Order[]>;
}

// src/ports/customer-repository.ts
export interface CustomerRepository {
  exists(customerId: string): Promise<boolean>;
}

// src/ports/inventory-repository.ts
export interface InventoryRepository {
  checkStock(productId: string, quantity: number): Promise<boolean>;
}

// src/use-cases/create-order.ts
import { randomUUID } from 'crypto';
import { ok, err } from '../domain/result';
import type { Result } from '../domain/result';
import type { Order, OrderLine } from '../domain/order';
import {
  CustomerNotFoundError,
  EmptyOrderError,
  InsufficientStockError,
  type CreateOrderError,
} from '../domain/errors';
import type { OrderRepository } from '../ports/order-repository';
import type { CustomerRepository } from '../ports/customer-repository';
import type { InventoryRepository } from '../ports/inventory-repository';

export interface CreateOrderInput {
  customerId: string;
  lines: OrderLine[];
}

export class CreateOrderUseCase {
  constructor(
    private readonly orders: OrderRepository,
    private readonly customers: CustomerRepository,
    private readonly inventory: InventoryRepository
  ) {}

  async execute(input: CreateOrderInput): Promise<Result<Order, CreateOrderError>> {
    if (input.lines.length === 0) {
      return err(new EmptyOrderError());
    }

    const customerExists = await this.customers.exists(input.customerId);
    if (!customerExists) {
      return err(new CustomerNotFoundError(input.customerId));
    }

    for (const line of input.lines) {
      const inStock = await this.inventory.checkStock(line.productId, line.quantity);
      if (!inStock) {
        return err(new InsufficientStockError(line.productId));
      }
    }

    const totalCents = input.lines.reduce(
      (sum, l) => sum + l.priceCents * l.quantity,
      0
    );

    const order: Order = {
      id: randomUUID(),
      customerId: input.customerId,
      lines: input.lines,
      totalCents,
      status: 'pending',
      createdAt: new Date().toISOString(),
    };

    await this.orders.save(order);
    return ok(order);
  }
}

// src/adapters/d1-order-repository.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { OrderRepository } from '../ports/order-repository';
import type { Order } from '../domain/order';

export class D1OrderRepository implements OrderRepository {
  constructor(private readonly db: D1Database) {}

  async save(order: Order): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO orders (id, customer_id, total_cents, status, created_at, lines_json)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET status=excluded.status`
      )
      .bind(
        order.id,
        order.customerId,
        order.totalCents,
        order.status,
        order.createdAt,
        JSON.stringify(order.lines)
      )
      .run();
  }

  async findById(id: string): Promise<Order | null> {
    const row = await this.db
      .prepare('SELECT * FROM orders WHERE id = ?')
      .bind(id)
      .first<{ id: string; customer_id: string; total_cents: number; status: string; created_at: string; lines_json: string }>();
    if (!row) return null;
    return {
      id: row.id,
      customerId: row.customer_id,
      totalCents: row.total_cents,
      status: row.status as Order['status'],
      createdAt: row.created_at,
      lines: JSON.parse(row.lines_json),
    };
  }

  async findByCustomer(customerId: string, limit: number): Promise<Order[]> {
    const result = await this.db
      .prepare('SELECT * FROM orders WHERE customer_id = ? LIMIT ?')
      .bind(customerId, limit)
      .all<{ id: string; customer_id: string; total_cents: number; status: string; created_at: string; lines_json: string }>();
    return result.results.map((row) => ({
      id: row.id,
      customerId: row.customer_id,
      totalCents: row.total_cents,
      status: row.status as Order['status'],
      createdAt: row.created_at,
      lines: JSON.parse(row.lines_json),
    }));
  }
}

// src/index.ts  (thin HTTP adapter — no business logic)
import { CreateOrderUseCase } from './use-cases/create-order';
import { D1OrderRepository } from './adapters/d1-order-repository';

class D1CustomerRepository {
  constructor(private readonly db: D1Database) {}
  async exists(customerId: string): Promise<boolean> {
    const row = await this.db.prepare('SELECT 1 FROM customers WHERE id = ?').bind(customerId).first();
    return row !== null;
  }
}

class D1InventoryRepository {
  constructor(private readonly db: D1Database) {}
  async checkStock(productId: string, quantity: number): Promise<boolean> {
    const row = await this.db
      .prepare('SELECT quantity FROM inventory WHERE product_id = ?')
      .bind(productId)
      .first<{ quantity: number }>();
    return row !== null && row.quantity >= quantity;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/orders') {
      return new Response('Not found', { status: 404 });
    }

    const body = await request.json<{ customerId: string; lines: unknown[] }>();

    const useCase = new CreateOrderUseCase(
      new D1OrderRepository(env.DB),
      new D1CustomerRepository(env.DB),
      new D1InventoryRepository(env.DB)
    );

    const result = await useCase.execute({
      customerId: body.customerId,
      lines: body.lines as never,
    });

    if (!result.ok) {
      const status =
        result.error.type === 'CustomerNotFound' ? 404
        : result.error.type === 'EmptyOrder'     ? 400
        : result.error.type === 'InsufficientStock' ? 409
        : 500;
      return Response.json({ error: result.error.message }, { status });
    }

    return Response.json(result.value, { status: 201 });
  },
};
```

---

## Section 3 — Vitest Tests with In-Memory Repository

```typescript
// tests/create-order.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { CreateOrderUseCase } from '../src/use-cases/create-order';
import type { OrderRepository } from '../src/ports/order-repository';
import type { CustomerRepository } from '../src/ports/customer-repository';
import type { InventoryRepository } from '../src/ports/inventory-repository';
import type { Order } from '../src/domain/order';

class InMemoryOrderRepository implements OrderRepository {
  private store = new Map<string, Order>();
  async save(order: Order): Promise<void> { this.store.set(order.id, order); }
  async findById(id: string): Promise<Order | null> { return this.store.get(id) ?? null; }
  async findByCustomer(customerId: string, limit: number): Promise<Order[]> {
    return [...this.store.values()].filter((o) => o.customerId === customerId).slice(0, limit);
  }
}

class StubCustomerRepository implements CustomerRepository {
  constructor(private readonly knownIds: Set<string>) {}
  async exists(id: string): Promise<boolean> { return this.knownIds.has(id); }
}

class StubInventoryRepository implements InventoryRepository {
  constructor(private readonly inStock: Set<string>) {}
  async checkStock(productId: string, _qty: number): Promise<boolean> {
    return this.inStock.has(productId);
  }
}

describe('CreateOrderUseCase', () => {
  let orders: InMemoryOrderRepository;
  let customers: StubCustomerRepository;
  let inventory: StubInventoryRepository;
  let useCase: CreateOrderUseCase;

  beforeEach(() => {
    orders = new InMemoryOrderRepository();
    customers = new StubCustomerRepository(new Set(['cust-1']));
    inventory = new StubInventoryRepository(new Set(['prod-a', 'prod-b']));
    useCase = new CreateOrderUseCase(orders, customers, inventory);
  });

  it('creates an order for a valid customer with stock', async () => {
    const result = await useCase.execute({
      customerId: 'cust-1',
      lines: [{ productId: 'prod-a', quantity: 2, priceCents: 1000 }],
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.totalCents).toBe(2000);
      expect(result.value.status).toBe('pending');
    }
  });

  it('returns EmptyOrderError when lines are empty', async () => {
    const result = await useCase.execute({ customerId: 'cust-1', lines: [] });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.type).toBe('EmptyOrder');
  });

  it('returns CustomerNotFoundError for unknown customer', async () => {
    const result = await useCase.execute({
      customerId: 'unknown',
      lines: [{ productId: 'prod-a', quantity: 1, priceCents: 500 }],
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.type).toBe('CustomerNotFound');
  });

  it('returns InsufficientStockError when product is out of stock', async () => {
    const result = await useCase.execute({
      customerId: 'cust-1',
      lines: [{ productId: 'out-of-stock-prod', quantity: 1, priceCents: 200 }],
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.type).toBe('InsufficientStock');
  });
});
```

---

## Anti-patterns
- **Returning `Result` that wraps another `Result`** — flatten your types; a use case should return `Result<Order, CreateOrderError>` not `Result<Result<Order>>`.
- **Importing `env` or Workers bindings inside a use case** — the use case must be portable; any infra dependency belongs in a repository adapter.
- **Throwing inside `execute` for expected domain errors** — use the `err()` path so callers get type-safe error discrimination without try/catch.

---

## Gotchas
- The `Result` discriminated union requires TypeScript 4.9+ for proper narrowing with `if (result.ok)`; older versions may need `result.ok === true`.
- `randomUUID()` from the Node `crypto` module is available in Workers via the Web Crypto API as `crypto.randomUUID()` — prefer the global to avoid a Node import that breaks in edge runtimes.
- In-memory repositories used in tests must match the exact async signatures of the port; `async () => value` satisfies `Promise<T>` even without `await`.

---

## Verification

```bash
# Run unit tests — no Workers runtime needed
npx vitest run tests/create-order.test.ts

# Apply D1 schema
wrangler d1 execute <db-name> --file=migrations/0001_orders.sql

# Create an order (customer + inventory must exist in DB)
curl -X POST https://<worker>.workers.dev/orders \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"cust-1","lines":[{"productId":"prod-a","quantity":1,"priceCents":2999}]}'

# Expect 201 with order JSON or a typed error body
```

---

## Related
- `workers-hexagonal-ports-adapters.md`
- `workers-cqrs-d1-read-write-separation.md`
- `workers-event-driven-fanout-queues.md`

---

## Sources
- Robert C. Martin — Clean Architecture — https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Vitest documentation — https://vitest.dev/
