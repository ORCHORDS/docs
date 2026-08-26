# Durable Objects SQL API Batch Transaction Pattern — Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Durable Object (DO) needs to atomically commit multiple related SQL writes — e.g. creating an order, decrementing inventory, and appending an audit log row — in a single transaction via the `storage.sql` API. The naive approach of calling `storage.sql.exec()` three times independently is not atomic; a DO alarm or eviction between calls can leave the database in a partial state.

---

## Context

Durable Objects with the SQLite Storage API (`storage.sql`) expose a synchronous, embedded SQLite database local to each DO instance. Unlike D1, the DO SQL API is **synchronous** — you call `storage.sql.exec(sql, ...bindings)` and get a cursor back immediately (no Promises). This makes transaction batching straightforward but requires careful structuring to avoid holding locks longer than necessary.

Key facts about DO SQL transactions:

| Behaviour | Detail |
|---|---|
| Transaction scope | A single `BEGIN … COMMIT` block per batch |
| Rollback on exception | Must be explicit: `ROLLBACK` in the catch block |
| Cursor iteration | Cursors are lazy — drain them inside the transaction if you need row data |
| DO restart safety | `ctx.storage.sql` persists across DO evictions; uncommitted transactions roll back |
| Alarm interaction | Alarms fire in a new activation — a transaction open in a previous activation is gone |

---

## Basic Batch Transaction Helper

```typescript
// src/lib/do-sql-transaction.ts

type SqlExec = DurableObjectStorage["sql"]["exec"];

export interface SqlBatch {
  sql: string;
  bindings?: (string | number | null | ArrayBuffer)[];
}

export interface BatchResult {
  rowsWritten: number;
  durationMs: number;
}

/**
 * Execute an array of SQL statements as a single atomic transaction
 * using the Durable Object synchronous SQL API.
 *
 * Rolls back automatically on any exception and re-throws.
 */
export function execBatchTransaction(
  exec: SqlExec,
  statements: SqlBatch[]
): BatchResult {
  const start = Date.now();
  let rowsWritten = 0;

  exec("BEGIN");
  try {
    for (const { sql, bindings = [] } of statements) {
      const cursor = exec(sql, ...bindings);
      // rowsWritten is available on the cursor after exec
      rowsWritten += cursor.rowsWritten ?? 0;
    }
    exec("COMMIT");
  } catch (err) {
    exec("ROLLBACK");
    throw err;
  }

  return { rowsWritten, durationMs: Date.now() - start };
}
```

---

## Durable Object Class with Batch Transactions

```typescript
// src/durable-objects/order-do.ts
import { execBatchTransaction, type SqlBatch } from "../lib/do-sql-transaction";

export interface Env {
  ORDER_DO: DurableObjectNamespace;
}

interface OrderPayload {
  orderId: string;
  productId: string;
  quantity: number;
  userId: string;
  totalCents: number;
}

export class OrderDurableObject implements DurableObject {
  private readonly sql: DurableObjectStorage["sql"];

  constructor(private readonly ctx: DurableObjectState, private readonly env: Env) {
    this.sql = ctx.storage.sql;
    this.initSchema();
  }

  private initSchema(): void {
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS orders (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        total_cents INTEGER NOT NULL,
        status      TEXT NOT NULL DEFAULT 'pending',
        created_at  TEXT NOT NULL
      )
    `);
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS inventory (
        product_id TEXT PRIMARY KEY,
        quantity   INTEGER NOT NULL CHECK (quantity >= 0)
      )
    `);
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS audit_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        payload    TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
    `);
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/order") {
      const payload = await request.json<OrderPayload>();
      const result = this.createOrder(payload);
      return Response.json(result);
    }

    return new Response("Not found", { status: 404 });
  }

  createOrder(payload: OrderPayload): { orderId: string; rowsWritten: number } {
    const now = new Date().toISOString();

    const statements: SqlBatch[] = [
      // 1. Insert the order
      {
        sql: `INSERT INTO orders (id, user_id, total_cents, status, created_at)
              VALUES (?1, ?2, ?3, 'pending', ?4)`,
        bindings: [payload.orderId, payload.userId, payload.totalCents, now],
      },
      // 2. Decrement inventory (CHECK constraint prevents negative stock)
      {
        sql: `UPDATE inventory
              SET quantity = quantity - ?1
              WHERE product_id = ?2`,
        bindings: [payload.quantity, payload.productId],
      },
      // 3. Append audit log
      {
        sql: `INSERT INTO audit_log (event_type, payload, created_at)
              VALUES ('ORDER_CREATED', json_object(
                'order_id', ?1,
                'user_id',  ?2,
                'product_id', ?3,
                'quantity', ?4
              ), ?5)`,
        bindings: [
          payload.orderId,
          payload.userId,
          payload.productId,
          payload.quantity,
          now,
        ],
      },
    ];

    const { rowsWritten } = execBatchTransaction(this.sql.exec.bind(this.sql), statements);

    return { orderId: payload.orderId, rowsWritten };
  }
}
```

---

## Reading Data Inside a Transaction

When you need to read a row *and* conditionally update it atomically, open an explicit transaction and drain the cursor before committing:

```typescript
// src/lib/do-sql-read-modify-write.ts

type SqlExec = DurableObjectStorage["sql"]["exec"];

export interface TransferParams {
  fromId: string;
  toId: string;
  amountCents: number;
}

/**
 * Atomic read-modify-write: transfer balance between two accounts.
 * Uses serializable isolation of the DO's single-writer model.
 */
export function transferBalance(exec: SqlExec, params: TransferParams): void {
  exec("BEGIN");
  try {
    // Read source balance
    const cursor = exec(
      "SELECT balance_cents FROM accounts WHERE id = ?1",
      params.fromId
    );

    // Drain the cursor inside the transaction
    const rows = [...cursor];
    if (rows.length === 0) {
      throw new Error(`Account ${params.fromId} not found`);
    }

    const balance = (rows[0] as any).balance_cents as number;
    if (balance < params.amountCents) {
      throw new Error(`Insufficient funds: have ${balance}, need ${params.amountCents}`);
    }

    // Debit source
    exec(
      "UPDATE accounts SET balance_cents = balance_cents - ?1 WHERE id = ?2",
      params.amountCents,
      params.fromId
    );

    // Credit destination
    exec(
      "UPDATE accounts SET balance_cents = balance_cents + ?1 WHERE id = ?2",
      params.amountCents,
      params.toId
    );

    exec("COMMIT");
  } catch (err) {
    exec("ROLLBACK");
    throw err;
  }
}
```

---

## Savepoint-based Nested Batches

For complex workflows where an inner set of writes should roll back independently without aborting the outer transaction:

```typescript
// src/lib/do-sql-savepoint.ts

type SqlExec = DurableObjectStorage["sql"]["exec"];

export function execWithSavepoint(
  exec: SqlExec,
  savepointName: string,
  inner: () => void
): boolean {
  exec(`SAVEPOINT ${savepointName}`);
  try {
    inner();
    exec(`RELEASE SAVEPOINT ${savepointName}`);
    return true;
  } catch (err) {
    exec(`ROLLBACK TO SAVEPOINT ${savepointName}`);
    console.warn(`Savepoint ${savepointName} rolled back:`, err);
    return false; // Outer transaction still active
  }
}

// Usage inside an outer BEGIN...COMMIT:
//
// exec("BEGIN");
// try {
//   execWithSavepoint(exec, "sp_inventory", () => {
//     exec("UPDATE inventory SET quantity = quantity - 1 WHERE ...");
//   });
//   exec("INSERT INTO orders ...");
//   exec("COMMIT");
// } catch (err) {
//   exec("ROLLBACK");
//   throw err;
// }
```

---

## DO Alarm Integration — Deferred Batch Commit

Use a DO alarm to batch writes that arrive during a time window and commit them together:

```typescript
// src/durable-objects/write-buffer-do.ts

interface PendingWrite {
  table: string;
  sql: string;
  bindings: (string | number | null)[];
}

export class WriteBufferDurableObject implements DurableObject {
  private pending: PendingWrite[] = [];
  private readonly sql: DurableObjectStorage["sql"];

  constructor(private readonly ctx: DurableObjectState, env: unknown) {
    this.sql = ctx.storage.sql;
  }

  async fetch(request: Request): Promise<Response> {
    const write = await request.json<PendingWrite>();
    this.pending.push(write);

    // Schedule flush 500 ms from now (alarm coalesces repeated calls)
    const existing = await this.ctx.storage.getAlarm();
    if (!existing) {
      await this.ctx.storage.setAlarm(Date.now() + 500);
    }

    return new Response("buffered", { status: 202 });
  }

  async alarm(): Promise<void> {
    if (this.pending.length === 0) return;

    const toFlush = this.pending.splice(0);

    try {
      execBatchTransaction(
        this.sql.exec.bind(this.sql),
        toFlush.map(({ sql, bindings }) => ({ sql, bindings }))
      );
      console.log(`Flushed ${toFlush.length} buffered writes`);
    } catch (err) {
      // Re-queue on failure
      this.pending.unshift(...toFlush);
      await this.ctx.storage.setAlarm(Date.now() + 2000);
      throw err;
    }
  }
}
```

---

## Anti-patterns

- **Running multiple `exec()` calls without `BEGIN/COMMIT`.** Each `exec()` outside an explicit transaction runs in its own implicit transaction. If the DO is evicted between calls, you get a partial write.
- **Forgetting `ROLLBACK` in the catch block.** SQLite will auto-rollback a transaction when the connection closes, but within a single DO activation an uncaught exception without `ROLLBACK` leaves the implicit transaction open and blocks future writes.
- **Draining cursors after `COMMIT`.** The cursor from an `exec()` inside a transaction becomes invalid after `COMMIT` or `ROLLBACK`. Always drain (iterate) before committing.
- **Long-running transactions with alarm interleaving.** If your transaction takes >10 ms and a DO alarm fires, the alarm runs in the same single-threaded environment but a transaction should complete well within a single synchronous call stack — never `await` inside a BEGIN/COMMIT block.
- **Using `IMMEDIATE` or `EXCLUSIVE` locking modes.** The DO SQL API's single-writer model makes these unnecessary and potentially harmful.

---

## Gotchas

- **`exec()` is synchronous but JS Promises are not.** Never place `exec()` calls inside `await` chains within a BEGIN/COMMIT block — the transaction is synchronous; mixing async operations will not keep the transaction open.
- **`rowsWritten` is 0 for SELECT.** Only `INSERT`, `UPDATE`, `DELETE` populate `rowsWritten` on the cursor. `SELECT` returns rows via cursor iteration.
- **DO SQL vs D1**: DO SQL runs embedded in the DO process; D1 is a remote service. DO SQL has no network latency but is single-instance per DO; D1 scales to many Workers simultaneously.
- **Storage limits**: Each DO SQLite database is limited to 1 GB of storage. Batch transactions do not change this limit; plan for archiving old rows to D1 or R2.
- **`ctx.blockConcurrencyWhile`**: For operations that combine DO storage (key-value) with SQL, wrap in `ctx.blockConcurrencyWhile(() => { ... })` to prevent interleaving with other incoming requests.

---

## Verification

```typescript
// Minimal integration test using Miniflare
import { Miniflare } from "miniflare";
import { describe, it, expect, beforeEach, afterEach } from "vitest";

describe("OrderDurableObject batch transaction", () => {
  let mf: Miniflare;

  beforeEach(async () => {
    mf = new Miniflare({
      modules: true,
      script: `
        export { OrderDurableObject } from "./src/durable-objects/order-do";
        export default { fetch: () => new Response("ok") };
      `,
      durableObjects: { ORDER_DO: "OrderDurableObject" },
    });
  });

  afterEach(async () => {
    await mf.dispose();
  });

  it("creates order atomically", async () => {
    const ns = await mf.getDurableObjectNamespace("ORDER_DO");
    const id = ns.idFromName("test-order");
    const stub = ns.get(id);

    const res = await stub.fetch("http://do/order", {
      method: "POST",
      body: JSON.stringify({
        orderId: "ord-1",
        productId: "prod-abc",
        quantity: 2,
        userId: "user-xyz",
        totalCents: 4000,
      }),
    });

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.orderId).toBe("ord-1");
  });
});
```

---

## Related

- `durable-objects-sql-storage-api-workers.md` — General DO SQL API overview
- `d1-savepoint-nested-transaction-workers.md` — Savepoints in D1 (remote) transactions
- `d1-durable-objects-serialized-writes-workers.md` — Serializing D1 writes through a DO
- `d1-optimistic-locking-version-column-workers.md` — Version-column approach for concurrency
- `d1-deferred-foreign-key-transaction-workers.md` — FK deferral patterns in transactions

---

## Sources

- Cloudflare Durable Objects SQL API: https://developers.cloudflare.com/durable-objects/api/storage-api/#sql-api
- SQLite transactions: https://www.sqlite.org/lang_transaction.html
- SQLite savepoints: https://www.sqlite.org/lang_savepoint.html
- Cloudflare DO alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
