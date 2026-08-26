# Unit of Work Pattern with D1 Batch in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A single business operation — e.g. "place an order" — touches multiple D1 tables. Individual
`await db.prepare(...).run()` calls succeed or fail independently. A network hiccup after the
first write leaves the database in a partial, inconsistent state with no way to roll back.

## Context

D1 supports `db.batch([...statements])` which executes an array of prepared statements in a
single HTTP round-trip and inside an implicit transaction: if any statement fails the entire
batch is rolled back. The Unit of Work (UoW) pattern provides a session-scoped collector that
accumulates D1 statements during a request and flushes them atomically at the end.

Key properties:
- All writes collected during a handler execute as one `db.batch()` call
- Partial failure rolls back the whole unit
- Optimistic concurrency checks are embedded as `WHERE version = ?` statements
- The UoW is constructed per-request, not shared between requests

---

## Section 1 — Unit of Work Class

```typescript
// src/infrastructure/db/UnitOfWork.ts

import type { D1Database, D1PreparedStatement } from '@cloudflare/workers-types';

export interface PendingStatement {
  label: string;
  statement: D1PreparedStatement;
}

export class UnitOfWork {
  private pending: PendingStatement[] = [];
  private committed = false;

  constructor(private readonly db: D1Database) {}

  /** Register a prepared statement to run inside the batch. */
  enqueue(label: string, statement: D1PreparedStatement): void {
    if (this.committed) {
      throw new Error(`UnitOfWork already committed; cannot enqueue '${label}'`);
    }
    this.pending.push({ label, statement });
  }

  /** Helper: prepare + bind + enqueue in one call. */
  add(label: string, sql: string, ...bindings: unknown[]): void {
    let stmt = this.db.prepare(sql);
    if (bindings.length) stmt = stmt.bind(...bindings);
    this.enqueue(label, stmt);
  }

  /** Execute all pending statements as a single D1 batch transaction. */
  async commit(): Promise<void> {
    if (this.committed) throw new Error('UnitOfWork already committed');
    if (this.pending.length === 0) {
      this.committed = true;
      return;
    }

    const statements = this.pending.map((p) => p.statement);
    try {
      await this.db.batch(statements);
      this.committed = true;
    } catch (err) {
      // D1 batch rolled back — surface a domain-friendly error
      const labels = this.pending.map((p) => p.label).join(', ');
      throw new Error(
        `UnitOfWork batch failed (operations: ${labels}): ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    }
  }

  get size(): number {
    return this.pending.length;
  }

  get isCommitted(): boolean {
    return this.committed;
  }
}
```

---

## Section 2 — Repositories Writing to a UoW

Repositories receive the UoW and call `uow.add()` instead of executing immediately. They never
hold a direct reference to `D1Database`.

```typescript
// src/infrastructure/repositories/OrderRepository.ts

import type { UnitOfWork } from '../db/UnitOfWork';

export interface Order {
  id: string;
  userId: string;
  totalCents: number;
  status: 'pending' | 'confirmed' | 'cancelled';
  version: number;
}

export class OrderRepository {
  constructor(private readonly uow: UnitOfWork) {}

  insertOrder(order: Order): void {
    this.uow.add(
      'insert-order',
      `INSERT INTO orders (id, user_id, total_cents, status, version)
       VALUES (?1, ?2, ?3, ?4, ?5)`,
      order.id,
      order.userId,
      order.totalCents,
      order.status,
      order.version
    );
  }

  /**
   * Optimistic concurrency: the WHERE clause checks the current version.
   * If another process bumped the version the statement matches 0 rows,
   * D1 does not error — callers must inspect meta.changes post-commit
   * or use a separate read to detect conflicts before building the UoW.
   */
  confirmOrder(id: string, expectedVersion: number): void {
    this.uow.add(
      'confirm-order',
      `UPDATE orders SET status = 'confirmed', version = version + 1
       WHERE id = ?1 AND version = ?2`,
      id,
      expectedVersion
    );
  }
}

// src/infrastructure/repositories/InventoryRepository.ts

import type { UnitOfWork } from '../db/UnitOfWork';

export class InventoryRepository {
  constructor(private readonly uow: UnitOfWork) {}

  decrementStock(skuId: string, qty: number): void {
    this.uow.add(
      'decrement-stock',
      `UPDATE inventory SET quantity = quantity - ?1
       WHERE sku_id = ?2 AND quantity >= ?1`,
      qty,
      skuId
    );
  }
}
```

---

## Section 3 — Domain Service Flushing the UoW

```typescript
// src/domain/services/PlaceOrderService.ts

import { UnitOfWork } from '../../infrastructure/db/UnitOfWork';
import { OrderRepository } from '../../infrastructure/repositories/OrderRepository';
import { InventoryRepository } from '../../infrastructure/repositories/InventoryRepository';
import type { D1Database } from '@cloudflare/workers-types';

export interface PlaceOrderCommand {
  orderId: string;
  userId: string;
  skuId: string;
  quantity: number;
  totalCents: number;
}

export async function placeOrder(
  db: D1Database,
  command: PlaceOrderCommand
): Promise<void> {
  const uow = new UnitOfWork(db);
  const orders = new OrderRepository(uow);
  const inventory = new InventoryRepository(uow);

  orders.insertOrder({
    id: command.orderId,
    userId: command.userId,
    totalCents: command.totalCents,
    status: 'pending',
    version: 1,
  });

  inventory.decrementStock(command.skuId, command.quantity);

  // Both statements commit atomically; failure rolls back both
  await uow.commit();
}
```

---

## Section 4 — Optimistic Concurrency with Version Checking

Because D1 does not raise an error when `UPDATE ... WHERE version = ?` matches 0 rows, read
the entity first and fail fast before building the UoW.

```typescript
// src/domain/services/ConfirmOrderService.ts

import type { D1Database } from '@cloudflare/workers-types';
import { UnitOfWork } from '../../infrastructure/db/UnitOfWork';
import { OrderRepository } from '../../infrastructure/repositories/OrderRepository';

export class OptimisticLockError extends Error {
  constructor(orderId: string) {
    super(`Optimistic lock conflict on order ${orderId}`);
    this.name = 'OptimisticLockError';
  }
}

export async function confirmOrder(
  db: D1Database,
  orderId: string
): Promise<void> {
  // Read-then-write: get current version before opening the UoW
  const row = await db
    .prepare('SELECT version FROM orders WHERE id = ?1')
    .bind(orderId)
    .first<{ version: number }>();

  if (!row) throw new Error(`Order ${orderId} not found`);

  const expectedVersion = row.version;

  const uow = new UnitOfWork(db);
  const orders = new OrderRepository(uow);

  orders.confirmOrder(orderId, expectedVersion);

  await uow.commit();

  // After commit, verify the row was actually updated
  const updated = await db
    .prepare('SELECT version FROM orders WHERE id = ?1')
    .bind(orderId)
    .first<{ version: number }>();

  if (!updated || updated.version !== expectedVersion + 1) {
    throw new OptimisticLockError(orderId);
  }
}
```

---

## Anti-patterns

- **Calling `uow.commit()` inside a loop** — defeats the purpose; accumulate all statements first, then commit once.
- **Sharing a UoW across requests** — the UoW is a per-request object. A global instance leads to cross-request contamination.
- **Assuming D1 batch is serializable isolation** — D1 batch is atomic but runs at snapshot isolation; external reads between batch items are not re-checked.
- **Forgetting to await commit** — fire-and-forget `uow.commit()` silently swallows errors.

## Gotchas

- `db.batch()` has a statement limit (currently 100 per batch in D1). For bulk imports, chunk the work.
- D1 batch throws on the *first* failing statement; subsequent statements in the array are never executed.
- `result.meta.changes` from individual batch results is not available from the top-level `db.batch()` return; destructure the results array: `const [r1, r2] = await db.batch([s1, s2])`.
- The `committed` guard prevents double-commit bugs but does not prevent forgetting to commit entirely — consider a finalizer check in middleware.

## Verification

```bash
# Verify batch atomicity locally
npx wrangler d1 execute DB --local --command \
  "INSERT INTO orders VALUES ('o1','u1',100,'pending',1);"

npx vitest run src/domain/services/PlaceOrderService.test.ts
```

## Related

- `workers-repository-pattern-d1.md` — repository interfaces consumed by the UoW
- `workers-domain-event-dispatcher-queues.md` — emitting domain events after UoW commit

## Sources

- [Cloudflare D1 Batch documentation](https://developers.cloudflare.com/d1/worker-api/d1-database/#batch)
- Fowler, M. (2002). *Patterns of Enterprise Application Architecture*. Addison-Wesley. Unit of Work pattern.
