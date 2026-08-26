# Unit of Work Pattern: Batching D1 Mutations in a Single Transaction

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Workers handler that creates an order, deducts inventory, and appends an audit log entry sends three separate D1 statements. If the Worker crashes between the second and third write, the database is left in a partially consistent state. Tracking "what changed during this request" is scattered across the handler, and retry logic is duplicated at every call site.

Classic signs:
- Multiple `env.DB.prepare(...).run()` calls in sequence with no enclosing transaction
- Inconsistent data after a deploy-time crash or timeout mid-handler
- Tests that must mock three separate DB calls to exercise one business flow
- Rolling back a business operation requires manually issuing compensating `DELETE`/`UPDATE` statements

---

## Context

The Unit of Work pattern tracks all database mutations accumulated during a single business operation and commits them atomically. Nothing is written to the database until `commit()` is called; if any part of the operation fails, `rollback()` discards all pending changes. In the D1 context, D1's `batch()` API executes an array of prepared statements in a single SQLite transaction, making it the ideal commit mechanism.

```
Handler
  │
  ▼
UnitOfWork.register(stmt1)
UnitOfWork.register(stmt2)
UnitOfWork.register(stmt3)
  │
  ▼  commit()
  ──► D1.batch([stmt1, stmt2, stmt3])  ← single atomic transaction
```

The Unit of Work also provides a natural seam for collecting domain events that should be published only after the transaction succeeds.

---

## Core Unit of Work Class

```typescript
// src/db/unit-of-work.ts

export interface PendingStatement {
  label: string; // human-readable description for debugging
  stmt: D1PreparedStatement;
}

export class UnitOfWork {
  private pending: PendingStatement[] = [];
  private committed = false;
  private afterCommitCallbacks: Array<() => Promise<void>> = [];

  constructor(private readonly db: D1Database) {}

  /** Register a prepared statement to be executed inside the transaction. */
  register(label: string, stmt: D1PreparedStatement): this {
    if (this.committed) throw new Error("UnitOfWork already committed");
    this.pending.push({ label, stmt });
    return this; // fluent API
  }

  /** Register a callback to run after successful commit (e.g., publish events). */
  onCommit(callback: () => Promise<void>): this {
    this.afterCommitCallbacks.push(callback);
    return this;
  }

  /** Execute all registered statements as a single D1 batch transaction. */
  async commit(): Promise<D1Result[]> {
    if (this.committed) throw new Error("UnitOfWork already committed");
    if (this.pending.length === 0) {
      this.committed = true;
      return [];
    }

    const results = await this.db.batch(this.pending.map((p) => p.stmt));
    this.committed = true;

    // Run after-commit side effects in order; do not let them roll back the DB write
    for (const cb of this.afterCommitCallbacks) {
      try {
        await cb();
      } catch (err) {
        console.error("[unit-of-work] after-commit callback failed:", err);
      }
    }

    return results;
  }

  /** Discard all pending statements without writing to D1. */
  rollback(): void {
    this.pending = [];
    this.committed = true; // prevent accidental re-use
  }

  get pendingCount(): number {
    return this.pending.length;
  }

  get labels(): string[] {
    return this.pending.map((p) => p.label);
  }
}
```

---

## Repository Functions That Accept a Unit of Work

```typescript
// src/db/order-repository.ts
import type { UnitOfWork } from "./unit-of-work";

export interface OrderRow {
  id: string;
  user_id: string;
  total_cents: number;
  status: string;
  created_at: string;
}

export function insertOrder(db: D1Database, uow: UnitOfWork, order: Omit<OrderRow, "created_at">) {
  const createdAt = new Date().toISOString();
  const stmt = db
    .prepare(`INSERT INTO orders (id, user_id, total_cents, status, created_at) VALUES (?, ?, ?, ?, ?)`)
    .bind(order.id, order.user_id, order.total_cents, order.status, createdAt);
  uow.register("insert-order", stmt);
  return createdAt; // return computed value so caller can use it without waiting for commit
}

export function deductInventory(db: D1Database, uow: UnitOfWork, productId: string, quantity: number) {
  const stmt = db
    .prepare(`UPDATE inventory SET quantity = quantity - ? WHERE product_id = ? AND quantity >= ?`)
    .bind(quantity, productId, quantity);
  uow.register(`deduct-inventory:${productId}`, stmt);
}

export function appendAuditLog(
  db: D1Database,
  uow: UnitOfWork,
  entry: { id: string; actor: string; action: string; payload: string }
) {
  const stmt = db
    .prepare(`INSERT INTO audit_log (id, actor, action, payload, occurred_at) VALUES (?, ?, ?, ?, ?)`)
    .bind(entry.id, entry.actor, entry.action, entry.payload, new Date().toISOString());
  uow.register("append-audit-log", stmt);
}
```

---

## Worker: Orchestrating a Multi-Table Write

```typescript
// src/worker.ts
import type { Env } from "./types";
import { UnitOfWork } from "./db/unit-of-work";
import { insertOrder, deductInventory, appendAuditLog } from "./db/order-repository";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/orders") {
      return new Response("Not found", { status: 404 });
    }

    const body = await request.json<{
      userId: string;
      productId: string;
      quantity: number;
      unitCents: number;
    }>();

    const orderId = crypto.randomUUID();
    const totalCents = body.quantity * body.unitCents;

    const uow = new UnitOfWork(env.DB);

    const createdAt = insertOrder(env.DB, uow, {
      id: orderId,
      user_id: body.userId,
      total_cents: totalCents,
      status: "pending",
    });

    deductInventory(env.DB, uow, body.productId, body.quantity);

    appendAuditLog(env.DB, uow, {
      id: crypto.randomUUID(),
      actor: body.userId,
      action: "order.created",
      payload: JSON.stringify({ orderId, productId: body.productId, quantity: body.quantity }),
    });

    // Register a post-commit side effect (e.g., publish event to a queue)
    uow.onCommit(async () => {
      await env.ORDER_QUEUE.send({ type: "order.created", orderId, userId: body.userId });
    });

    let results: D1Result[];
    try {
      results = await uow.commit();
    } catch (err) {
      // D1 batch failed atomically — no partial writes occurred
      console.error("[orders] commit failed:", err);
      return Response.json({ error: "Order creation failed" }, { status: 500 });
    }

    // Verify inventory deduction actually matched a row
    const inventoryResult = results[1]; // second registered statement
    if (inventoryResult.meta.changes === 0) {
      // D1 batch already committed — compensate by cancelling the order
      await env.DB.prepare(`UPDATE orders SET status = 'cancelled' WHERE id = ?`)
        .bind(orderId)
        .run();
      return Response.json({ error: "Insufficient inventory" }, { status: 409 });
    }

    return Response.json({ orderId, status: "pending", createdAt }, { status: 201 });
  },
};
```

---

## Testing the Unit of Work in Isolation

```typescript
// src/db/__tests__/unit-of-work.test.ts
import { describe, it, expect, vi } from "vitest";
import { UnitOfWork } from "../unit-of-work";

function makeDb(batchResults: D1Result[]) {
  return {
    batch: vi.fn().mockResolvedValue(batchResults),
    prepare: vi.fn().mockReturnValue({ bind: vi.fn().mockReturnValue({}) }),
  } as unknown as D1Database;
}

it("executes all registered statements in batch", async () => {
  const db = makeDb([{ meta: { changes: 1 } } as D1Result, { meta: { changes: 1 } } as D1Result]);
  const uow = new UnitOfWork(db);
  uow.register("stmt-a", db.prepare("").bind());
  uow.register("stmt-b", db.prepare("").bind());
  const results = await uow.commit();
  expect(db.batch).toHaveBeenCalledTimes(1);
  expect(results).toHaveLength(2);
});

it("throws if committed twice", async () => {
  const db = makeDb([]);
  const uow = new UnitOfWork(db);
  await uow.commit();
  await expect(uow.commit()).rejects.toThrow("already committed");
});

it("runs onCommit callbacks after batch", async () => {
  const db = makeDb([{ meta: { changes: 1 } } as D1Result]);
  const uow = new UnitOfWork(db);
  uow.register("s", db.prepare("").bind());
  const cb = vi.fn().mockResolvedValue(undefined);
  uow.onCommit(cb);
  await uow.commit();
  expect(cb).toHaveBeenCalledTimes(1);
});

it("rollback prevents commit", async () => {
  const db = makeDb([]);
  const uow = new UnitOfWork(db);
  uow.register("s", db.prepare("").bind());
  uow.rollback();
  await expect(uow.commit()).rejects.toThrow("already committed");
  expect(db.batch).not.toHaveBeenCalled();
});
```

---

## Anti-patterns

- **Calling `env.DB.prepare().run()` outside the Unit of Work**: Ad-hoc DB calls bypass the transaction boundary. All writes in a business operation must be registered through the same `UnitOfWork` instance.
- **Using the Unit of Work as a long-lived singleton**: The `UnitOfWork` instance must be scoped to a single request. Reusing it across requests merges unrelated mutations into one transaction.
- **Performing network I/O inside `register()`**: `register()` must only create and enqueue a prepared statement. Async side effects belong in `onCommit` callbacks, not in the registration phase.
- **Ignoring `D1Result.meta.changes` after batch**: D1 does not throw when an `UPDATE` matches zero rows. Check `results[i].meta.changes` to detect no-op writes (e.g., inventory already zero).
- **Exceeding D1 batch limits**: D1 `batch()` accepts up to 1 000 statements per call. Large import operations must chunk their Unit of Work into sub-batches.

---

## Gotchas

- D1 `batch()` executes all statements in an implicit transaction: if any statement throws a SQLite error (constraint violation, type mismatch), the entire batch is rolled back and the `batch()` promise rejects.
- D1 `batch()` does not support `RETURNING` clauses across statements; use `crypto.randomUUID()` to generate IDs client-side before registering inserts, as shown in `insertOrder`.
- `onCommit` callbacks run after the batch succeeds but are **not** transactional—a callback failure cannot roll back D1. Use the Outbox pattern (`outbox-pattern-d1-reliable-publishing.md`) if post-commit event delivery must be guaranteed.
- Workers have a 30-second CPU time limit (50 ms on the free plan). Very large batches that take > 30 s on the D1 side will abort mid-commit. Keep batch sizes under a few hundred statements; use a Queue for bulk operations.
- The `committed` flag prevents accidental reuse but does not protect against concurrent access. Workers are single-threaded per request, so concurrent mutation is not possible within one isolate, but never share a `UnitOfWork` across `waitUntil` tasks.

---

## Verification

1. Insert an order with valid inventory; verify all three rows appear in `orders`, `inventory`, and `audit_log` after the request.
2. Attempt an order with quantity exceeding stock; verify `meta.changes === 0` for the inventory statement and the order row is cancelled.
3. Introduce a SQLite constraint violation on the audit log insert (e.g., duplicate `id`); verify the entire batch fails and neither the `orders` row nor the `inventory` deduction is committed.
4. Call `commit()` twice on the same `UnitOfWork`; verify the second call throws `"UnitOfWork already committed"`.
5. Verify `onCommit` callbacks are not called when `rollback()` is invoked before `commit()`.

---

## Related

- `outbox-pattern-d1-reliable-publishing.md` — durable post-commit event publishing
- `idempotency-key-pattern-workers-d1.md` — making the Unit of Work idempotency-safe
- `repository-pattern.md` — repository functions that register into a Unit of Work
- `database-transaction-design.md` — D1 transaction semantics and SQLite isolation levels

---

## Sources

- Fowler, Martin — Patterns of Enterprise Application Architecture (2002): Unit of Work
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- D1 batch transaction semantics: https://developers.cloudflare.com/d1/reference/transactions/
- SQLite implicit transactions: https://www.sqlite.org/lang_transaction.html
