# Unit of Work Pattern — D1 + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A single HTTP request modifies several aggregate roots (Order, Inventory, Customer credit). Without coordination, partial failures leave the database in an inconsistent state. Each domain service should not manage its own transaction.

## Context
Cloudflare D1 supports multi-statement transactions via `db.batch()` and `db.prepare().bind().run()` within a single `BEGIN`/`COMMIT` block. The Unit of Work (UoW) pattern collects all dirty objects registered during a request, then flushes them in a single atomic transaction at the end of the handler. This gives Workers the transactional semantics of a traditional ORM without pulling in a full ORM dependency.

---

## Architecture / Setup

```typescript
export interface Env {
  DB: D1Database;
}

// Discriminated union of all supported write operations
type WriteOp =
  | { kind: 'upsert_order'; orderId: string; status: string; total: number }
  | { kind: 'decrement_stock'; sku: string; qty: number }
  | { kind: 'debit_credit'; customerId: string; amount: number };

export class UnitOfWork {
  private ops: WriteOp[] = [];

  registerUpsertOrder(orderId: string, status: string, total: number): void {
    this.ops.push({ kind: 'upsert_order', orderId, status, total });
  }

  registerDecrementStock(sku: string, qty: number): void {
    this.ops.push({ kind: 'decrement_stock', sku, qty });
  }

  registerDebitCredit(customerId: string, amount: number): void {
    this.ops.push({ kind: 'debit_credit', customerId, amount });
  }

  get size(): number {
    return this.ops.length;
  }
}
```

## Flush Logic — Single Batch Transaction

```typescript
// Translate each WriteOp into a D1PreparedStatement
function toStatement(db: D1Database, op: WriteOp): D1PreparedStatement {
  switch (op.kind) {
    case 'upsert_order':
      return db
        .prepare(
          `INSERT INTO orders (id, status, total, updated_at)
           VALUES (?1, ?2, ?3, unixepoch())
           ON CONFLICT(id) DO UPDATE SET
             status = excluded.status,
             total = excluded.total,
             updated_at = excluded.updated_at`,
        )
        .bind(op.orderId, op.status, op.total);

    case 'decrement_stock':
      return db
        .prepare(
          `UPDATE inventory
           SET qty = qty - ?1, updated_at = unixepoch()
           WHERE sku = ?2 AND qty >= ?1`,
        )
        .bind(op.qty, op.sku);

    case 'debit_credit':
      return db
        .prepare(
          `UPDATE customer_credit
           SET balance = balance - ?1, updated_at = unixepoch()
           WHERE customer_id = ?2 AND balance >= ?1`,
        )
        .bind(op.amount, op.customerId);

    default:
      throw new Error(`Unknown op kind: ${(op as WriteOp).kind}`);
  }
}

export async function flush(uow: UnitOfWork, db: D1Database): Promise<void> {
  if (uow.size === 0) return;

  // Access private ops via a dedicated drain method
  const ops = (uow as unknown as { ops: WriteOp[] }).ops;
  const stmts = ops.map((op) => toStatement(db, op));

  const results = await db.batch(stmts);

  // Check for zero-row updates (optimistic lock / constraint violation)
  results.forEach((r, i) => {
    if (ops[i].kind !== 'upsert_order' && r.meta.changes === 0) {
      throw new Error(
        `UoW flush: zero rows affected for op[${i}] kind=${ops[i].kind}`,
      );
    }
  });
}
```

## Domain Service Integration

```typescript
// order-service.ts — domain logic registers ops, never calls DB directly
export class OrderService {
  constructor(private readonly uow: UnitOfWork) {}

  placeOrder(
    orderId: string,
    customerId: string,
    items: Array<{ sku: string; qty: number; price: number }>,
  ): void {
    const total = items.reduce((s, i) => s + i.qty * i.price, 0);

    this.uow.registerUpsertOrder(orderId, 'confirmed', total);
    this.uow.registerDebitCredit(customerId, total);

    for (const item of items) {
      this.uow.registerDecrementStock(item.sku, item.qty);
    }
  }
}

// Worker fetch handler — composes services with shared UoW
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const body = await req.json<{
      orderId: string;
      customerId: string;
      items: Array<{ sku: string; qty: number; price: number }>;
    }>();

    const uow = new UnitOfWork();
    const orderSvc = new OrderService(uow);

    try {
      orderSvc.placeOrder(body.orderId, body.customerId, body.items);
      await flush(uow, env.DB);
      return Response.json({ status: 'ok' });
    } catch (err) {
      console.error('uow_flush_failed', err);
      return Response.json(
        { error: (err as Error).message },
        { status: 409 },
      );
    }
  },
} satisfies ExportedHandler<Env>;
```

## Identity Map Extension (Optional)

```typescript
// Prevents duplicate SELECT queries for the same aggregate root
export class IdentityMap<K extends string | number, V> {
  private cache = new Map<K, V>();

  has(key: K): boolean {
    return this.cache.has(key);
  }

  get(key: K): V | undefined {
    return this.cache.get(key);
  }

  set(key: K, value: V): void {
    this.cache.set(key, value);
  }
}

// Usage: attach to UoW
export class UnitOfWorkWithIdentityMap extends UnitOfWork {
  readonly orders = new IdentityMap<string, { status: string; total: number }>();
  readonly inventory = new IdentityMap<string, { qty: number }>();
}
```

## Anti-patterns
- Flushing inside a domain service rather than at the handler boundary — creates nested transactions and lost-update windows
- Sharing a UoW across multiple concurrent requests — the UoW is per-request state; instantiate fresh for each handler invocation
- Swallowing `zero rows affected` results — they signal constraint violations (insufficient stock, negative credit) that must surface as errors
- Using `db.run()` inside a loop inside the UoW — defeats batching and causes N+1 round trips to D1

## Gotchas
- `db.batch()` in D1 executes statements sequentially in a single implicit transaction — ordering matters if statement N reads a row written by statement N-1
- D1 batch is capped at 100 statements per call; large orders must be chunked
- Workers CPU budget is 50 ms (Bundled) / 30 s (Unbound); flush at the end of the handler, not midway
- `meta.changes` reflects rows matching the WHERE clause that were actually changed, not rows matched — test with deliberate conflict scenarios

## Verification
```sql
-- Confirm atomic write: either all rows updated or none
SELECT o.id, o.status, o.total,
       cc.balance,
       i.qty
FROM orders o
JOIN customer_credit cc ON cc.customer_id = ?1
JOIN inventory i ON i.sku = ?2
WHERE o.id = ?3;

-- Check for orphaned partial writes (should return 0 after any failure)
SELECT COUNT(*) FROM orders
WHERE id = ?1 AND NOT EXISTS (
  SELECT 1 FROM customer_credit WHERE balance >= 0
);
```

## Related
- `repository-pattern-ddd.md`
- `aggregate-root-pattern.md`
- `optimistic-concurrency-control-d1.md`
- `d1-batch-operations-query-optimisation.md`
- `two-phase-commit-workers-d1-r2-coordination.md`

## Sources
- https://martinfowler.com/eaaCatalog/unitOfWork.html
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://developers.cloudflare.com/d1/reference/transactions/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/
