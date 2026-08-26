# Data Mapper Pattern: Separating Domain Objects from D1 Row Types

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

As D1 schemas evolve, handler code becomes littered with raw `SELECT *` rows, snake_case column names, and nullable fields that shouldn't leak into business logic. Coupling domain objects directly to DB row shapes makes schema migrations and unit testing painful.

## Context

- Runtime: Cloudflare Workers
- Database: Cloudflare D1 (SQLite dialect)
- Language: TypeScript 5.x
- Pattern: Data Mapper (Fowler, PoEAA) — a layer of objects that moves data between domain objects and the database while keeping them independent of each other and itself
- Anti-pattern avoided: Active Record (domain object knows how to save itself)

---

## 1. Domain Objects (no DB awareness)

```typescript
// src/domain/order.ts
export type OrderStatus = "pending" | "confirmed" | "shipped" | "cancelled";

export interface OrderLine {
  productId: string;
  quantity: number;
  unitPriceCents: number;
}

export class Order {
  constructor(
    public readonly id: string,
    public readonly customerId: string,
    public readonly lines: OrderLine[],
    public status: OrderStatus,
    public readonly createdAt: Date,
    public updatedAt: Date
  ) {}

  get totalCents(): number {
    return this.lines.reduce(
      (sum, l) => sum + l.quantity * l.unitPriceCents,
      0
    );
  }

  confirm(): void {
    if (this.status !== "pending") {
      throw new Error(`Cannot confirm order in status '${this.status}'`);
    }
    this.status = "confirmed";
    this.updatedAt = new Date();
  }

  cancel(): void {
    if (this.status === "shipped") {
      throw new Error("Cannot cancel a shipped order");
    }
    this.status = "cancelled";
    this.updatedAt = new Date();
  }
}
```

---

## 2. D1 Row Types (raw DB schema)

```typescript
// src/db/rows.ts

/** Mirrors the `orders` table columns exactly */
export interface OrderRow {
  id: string;
  customer_id: string;
  status: string;
  created_at: string;   // ISO-8601 text stored in D1
  updated_at: string;
}

/** Mirrors the `order_lines` table columns exactly */
export interface OrderLineRow {
  order_id: string;
  product_id: string;
  quantity: number;
  unit_price_cents: number;
}
```

---

## 3. Mapper Class

```typescript
// src/db/orderMapper.ts
import { Order, OrderLine, OrderStatus } from "../domain/order";
import { OrderRow, OrderLineRow } from "./rows";

export class OrderMapper {
  /**
   * DB rows → domain object.
   * Throws if the row data is structurally invalid.
   */
  static toDomain(row: OrderRow, lineRows: OrderLineRow[]): Order {
    const lines: OrderLine[] = lineRows.map((l) => ({
      productId: l.product_id,
      quantity: l.quantity,
      unitPriceCents: l.unit_price_cents,
    }));

    return new Order(
      row.id,
      row.customer_id,
      lines,
      row.status as OrderStatus,
      new Date(row.created_at),
      new Date(row.updated_at)
    );
  }

  /** Domain object → row shape for INSERT / UPDATE */
  static toRow(order: Order): OrderRow {
    return {
      id: order.id,
      customer_id: order.customerId,
      status: order.status,
      created_at: order.createdAt.toISOString(),
      updated_at: order.updatedAt.toISOString(),
    };
  }

  static toLineRows(order: Order): OrderLineRow[] {
    return order.lines.map((l) => ({
      order_id: order.id,
      product_id: l.productId,
      quantity: l.quantity,
      unit_price_cents: l.unitPriceCents,
    }));
  }
}
```

---

## 4. Repository Using the Mapper

```typescript
// src/db/orderRepository.ts
import { D1Database } from "@cloudflare/workers-types";
import { Order } from "../domain/order";
import { OrderRow, OrderLineRow } from "./rows";
import { OrderMapper } from "./orderMapper";

export class OrderRepository {
  constructor(private readonly db: D1Database) {}

  async findById(id: string): Promise<Order | null> {
    const [orderRow, lineRows] = await Promise.all([
      this.db
        .prepare("SELECT * FROM orders WHERE id = ?")
        .bind(id)
        .first<OrderRow>(),
      this.db
        .prepare("SELECT * FROM order_lines WHERE order_id = ?")
        .bind(id)
        .all<OrderLineRow>(),
    ]);

    if (!orderRow) return null;
    return OrderMapper.toDomain(orderRow, lineRows.results);
  }

  async save(order: Order): Promise<void> {
    const row = OrderMapper.toRow(order);
    const lineRows = OrderMapper.toLineRows(order);

    // Use a batch to keep header + lines atomic
    await this.db.batch([
      this.db
        .prepare(
          `INSERT INTO orders (id, customer_id, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             status = excluded.status,
             updated_at = excluded.updated_at`
        )
        .bind(row.id, row.customer_id, row.status, row.created_at, row.updated_at),
      // Replace lines atomically
      this.db
        .prepare("DELETE FROM order_lines WHERE order_id = ?")
        .bind(order.id),
      ...lineRows.map((l) =>
        this.db
          .prepare(
            `INSERT INTO order_lines (order_id, product_id, quantity, unit_price_cents)
             VALUES (?, ?, ?, ?)`
          )
          .bind(l.order_id, l.product_id, l.quantity, l.unit_price_cents)
      ),
    ]);
  }

  async findByCustomer(customerId: string): Promise<Order[]> {
    const { results: orderRows } = await this.db
      .prepare("SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC")
      .bind(customerId)
      .all<OrderRow>();

    if (orderRows.length === 0) return [];

    const ids = orderRows.map((r) => r.id);
    const placeholders = ids.map(() => "?").join(",");
    const { results: lineRows } = await this.db
      .prepare(`SELECT * FROM order_lines WHERE order_id IN (${placeholders})`)
      .bind(...ids)
      .all<OrderLineRow>();

    const linesByOrder = new Map<string, OrderLineRow[]>();
    for (const line of lineRows) {
      const list = linesByOrder.get(line.order_id) ?? [];
      list.push(line);
      linesByOrder.set(line.order_id, list);
    }

    return orderRows.map((row) =>
      OrderMapper.toDomain(row, linesByOrder.get(row.id) ?? [])
    );
  }
}
```

---

## 5. Handler (thin, uses domain + repository)

```typescript
// src/handlers/confirmOrder.ts
import { Env } from "../types";
import { OrderRepository } from "../db/orderRepository";

export async function handleConfirmOrder(
  req: Request,
  env: Env
): Promise<Response> {
  const { orderId } = await req.json<{ orderId: string }>();
  const repo = new OrderRepository(env.DB);
  const order = await repo.findById(orderId);
  if (!order) return Response.json({ error: "Order not found" }, { status: 404 });

  order.confirm(); // domain logic — no SQL here
  await repo.save(order);

  return Response.json({ status: order.status, total: order.totalCents });
}
```

---

## Anti-patterns

- **Active Record on domain classes**: adding `save()` / `delete()` methods to `Order` couples domain to D1 — breaks unit testing without a real database.
- **Leaking `OrderRow` into handlers**: handlers should only touch domain objects; raw row fields (`customer_id`, `created_at` strings) should never appear above the repository layer.
- **`SELECT *` in production queries**: enumerate columns explicitly so schema additions don't silently break mapper assumptions.
- **Mutable mapper state**: `OrderMapper` methods should be `static`; a stateful mapper is a maintenance trap.

## Gotchas

- D1 stores dates as text; `new Date(row.created_at)` works only if the value is a valid ISO-8601 string — enforce `DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))` in your DDL.
- `D1Database.batch()` is atomic per-batch but D1 does not support nested transactions — structure all mutations inside a single `batch` call.
- D1 `INT` columns come back as JavaScript `number`; amounts stored as cents avoid floating-point drift entirely.
- `first<T>()` returns `null` on no match, not `undefined` — check `=== null` explicitly.

## Verification

```bash
# Apply schema
wrangler d1 execute example project-db --file=migrations/0001_orders.sql

# Seed a row and fetch via handler
curl -s -X POST http://localhost:8787/orders/confirm \
  -H 'content-type: application/json' \
  -d '{"orderId":"ord_001"}' | jq .
# Expect: { "status": "confirmed", "total": <number> }

# Verify mapper round-trip in unit test
npx vitest run src/db/orderMapper.test.ts
```

## Related

- `documentation/docs/policies/architecture/workers-specification-pattern-d1-query-builder.md`
- `documentation/docs/policies/architecture/workers-api-gateway-aggregator-service-bindings.md`

## Sources

- https://developers.cloudflare.com/d1/reference/d1-client-api/
- https://developers.cloudflare.com/d1/reference/migrations/
- https://martinfowler.com/eaaCatalog/dataMapper.html
