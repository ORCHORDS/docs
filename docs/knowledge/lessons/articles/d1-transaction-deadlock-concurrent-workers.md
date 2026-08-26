# D1 Transaction Deadlock Between Concurrent Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
During a flash-sale event, two Workers — an order-placement Worker and an inventory-adjustment Worker — both opened D1 write transactions against the same tables in opposite order. Under concurrency, each transaction acquired a lock the other needed, producing SQLite `SQLITE_BUSY` errors that surfaced as HTTP 500s for 4–6% of requests over a 12-minute window.

## Context
Cloudflare D1 uses SQLite under the hood, which implements locking at the database level (not row or page level) for write transactions. SQLite's default journal mode is WAL (Write-Ahead Log), which allows concurrent readers but serialises writers. When two transactions each hold a read lock and attempt to escalate to a write lock, SQLite returns `SQLITE_BUSY` or `SQLITE_LOCKED`. D1 does not automatically retry on `SQLITE_BUSY` — the error propagates to the calling Worker as an exception. The deadlock was not a true circular lock (SQLite's WAL prevents that) but a write-lock contention pattern: two Workers trying to acquire the exclusive write lock simultaneously, each retrying in a tight loop and starving each other.

---

## Root Cause: Inconsistent Lock Acquisition Order and No Retry Back-off

```typescript
// workers/order-placement.ts — BUGGY
async function placeOrder(db: D1Database, orderId: string, skuId: string, qty: number) {
  const stmts = [
    db.prepare("INSERT INTO orders (id, sku_id, qty, status) VALUES (?, ?, ?, 'pending')")
      .bind(orderId, skuId, qty),
    // Writes orders FIRST, then inventory
    db.prepare("UPDATE inventory SET reserved = reserved + ? WHERE sku_id = ?")
      .bind(qty, skuId),
  ];
  await db.batch(stmts); // D1 batch — runs in an implicit transaction
}
```

```typescript
// workers/inventory-adjustment.ts — BUGGY
async function adjustInventory(db: D1Database, skuId: string, delta: number) {
  const stmts = [
    // Writes inventory FIRST, then audit — OPPOSITE ORDER from order-placement
    db.prepare("UPDATE inventory SET qty = qty + ? WHERE sku_id = ?")
      .bind(delta, skuId),
    db.prepare("INSERT INTO inventory_audit (sku_id, delta, ts) VALUES (?, ?, ?)")
      .bind(skuId, delta, Date.now()),
  ];
  await db.batch(stmts);
}
```

Both Workers used `db.batch()`, which wraps statements in an implicit transaction. Under concurrent traffic, both transactions attempted to upgrade their shared read lock to an exclusive write lock simultaneously; SQLite returned `SQLITE_BUSY` to the one that lost the race.

---

## Correct Pattern 1: Canonical Table-Access Order

Establish a global ordering for table writes and enforce it across all Workers. Alphabetical by table name is simple and auditable:

```typescript
// lib/db-order.ts — canonical write order
// Rule: inventory → inventory_audit → orders → order_items
// All Workers must acquire locks in this order

// workers/order-placement.ts — FIXED
async function placeOrder(db: D1Database, orderId: string, skuId: string, qty: number) {
  // inventory comes before orders per canonical order
  const stmts = [
    db.prepare("UPDATE inventory SET reserved = reserved + ? WHERE sku_id = ?")
      .bind(qty, skuId),
    db.prepare("INSERT INTO orders (id, sku_id, qty, status) VALUES (?, ?, ?, 'pending')")
      .bind(orderId, skuId, qty),
  ];
  await db.batch(stmts);
}

// workers/inventory-adjustment.ts — FIXED (already in correct order)
async function adjustInventory(db: D1Database, skuId: string, delta: number) {
  const stmts = [
    db.prepare("UPDATE inventory SET qty = qty + ? WHERE sku_id = ?")
      .bind(delta, skuId),
    db.prepare("INSERT INTO inventory_audit (sku_id, delta, ts) VALUES (?, ?, ?)")
      .bind(skuId, delta, Date.now()),
  ];
  await db.batch(stmts);
}
```

---

## Correct Pattern 2: Exponential Back-off Retry on SQLITE_BUSY

Even with canonical ordering, high-concurrency write spikes can still cause transient `SQLITE_BUSY`. Add a retry wrapper:

```typescript
// lib/d1-retry.ts
const BUSY_RE = /SQLITE_BUSY|database is locked/i;

export async function batchWithRetry(
  db: D1Database,
  stmts: D1PreparedStatement[],
  maxAttempts = 5,
): Promise<D1Result[]> {
  let attempt = 0;
  while (true) {
    attempt++;
    try {
      return await db.batch(stmts);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!BUSY_RE.test(msg) || attempt >= maxAttempts) {
        throw err; // propagate non-busy errors or exhausted retries
      }
      // Exponential back-off with jitter: 50ms, 100ms, 200ms, 400ms
      const delayMs = Math.min(50 * 2 ** (attempt - 1), 400)
        + Math.floor(Math.random() * 50);
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }
}
```

```typescript
// Usage in workers/order-placement.ts
import { batchWithRetry } from "../lib/d1-retry";

async function placeOrder(db: D1Database, orderId: string, skuId: string, qty: number) {
  const stmts = [
    db.prepare("UPDATE inventory SET reserved = reserved + ? WHERE sku_id = ?")
      .bind(qty, skuId),
    db.prepare("INSERT INTO orders (id, sku_id, qty, status) VALUES (?, ?, ?, 'pending')")
      .bind(orderId, skuId, qty),
  ];
  await batchWithRetry(db, stmts);
}
```

---

## Correct Pattern 3: Serialize High-Contention Writes via Durable Object

For tables with very high write contention (e.g., a single `inventory` row updated on every order), route all writes through a Durable Object — its single-threaded execution eliminates the contention entirely:

```typescript
// durable-objects/InventoryWriter.ts
export class InventoryWriter implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const { skuId, reserved, delta } = await request.json<{
      skuId: string;
      reserved?: number;
      delta?: number;
    }>();

    // All writes to this sku_id are serialized here
    const stmts: D1PreparedStatement[] = [];

    if (reserved !== undefined) {
      stmts.push(
        this.env.DB.prepare(
          "UPDATE inventory SET reserved = reserved + ? WHERE sku_id = ?"
        ).bind(reserved, skuId)
      );
    }
    if (delta !== undefined) {
      stmts.push(
        this.env.DB.prepare(
          "UPDATE inventory SET qty = qty + ? WHERE sku_id = ?"
        ).bind(delta, skuId),
        this.env.DB.prepare(
          "INSERT INTO inventory_audit (sku_id, delta, ts) VALUES (?, ?, ?)"
        ).bind(skuId, delta, Date.now())
      );
    }

    if (stmts.length > 0) {
      await this.env.DB.batch(stmts);
    }

    return Response.json({ ok: true });
  }
}
```

---

## Anti-patterns
- Acquiring locks in different table orders across different Workers or code paths — this is the classic deadlock recipe.
- Retrying `SQLITE_BUSY` in a tight loop (no sleep) — this starves the winning transaction by preventing it from finishing.
- Using `db.exec()` with multi-statement SQL for transactions — it wraps everything in a single implicit transaction with no retry hook.
- Assuming D1's WAL mode prevents all contention — WAL allows concurrent reads but still serialises writers.
- Not having integration tests that exercise concurrent writes against the same rows.

## Gotchas
- D1 `db.batch()` is an implicit transaction; all statements share a single write lock acquisition. If any statement fails (including `SQLITE_BUSY`), the entire batch is rolled back.
- `SQLITE_BUSY_SNAPSHOT` (WAL-specific) is a different error from `SQLITE_BUSY`; it occurs when a read transaction's snapshot is too old and a write cannot be completed. The retry logic above handles both.
- Workers CPU time counts while sleeping in `setTimeout`; long retry loops can hit the 30-second wall time limit. Keep `maxAttempts` low (3–5) and back-off short.
- The Durable Object serialization pattern adds ~1–5ms latency per write from cross-PoP DO routing; acceptable for inventory but not for sub-millisecond latency requirements.
- D1 is a globally distributed SQLite instance; the primary node that accepts writes can change during an incident. Retries may land on a different primary node and succeed.

## Verification

```bash
# Simulate concurrent writes with wrk
wrk -t8 -c50 -d30s -s concurrent-order.lua https://api.example.com/orders
# Watch for SQLITE_BUSY in Workers logs
wrangler tail --format=json | jq 'select(.exceptions[].message | test("SQLITE_BUSY"))'
```

```sql
-- Post-incident: verify no orphaned reservations (reserved > qty)
SELECT sku_id, qty, reserved
FROM inventory
WHERE reserved > qty;
-- Should return 0 rows

-- Verify audit log completeness
SELECT i.sku_id, i.qty, COALESCE(SUM(a.delta), 0) AS audit_total
FROM inventory i
LEFT JOIN inventory_audit a ON a.sku_id = i.sku_id
GROUP BY i.sku_id
HAVING i.qty != COALESCE(SUM(a.delta), 0);
-- Should return 0 rows if audit is complete
```

## Related
- `d1-write-contention-viral-event-postmortem.md`
- `durable-objects-storage-transaction-atomicity-lesson.md`
- `workers-kv-write-after-read-consistency-incident.md`
- `idempotency-keys-for-all-payment-calls.md`
- `queue-consumers-must-be-idempotent.md`

## Sources
- https://developers.cloudflare.com/d1/platform/client-api/#batch-statements
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/rescode.html#busy
- https://developers.cloudflare.com/durable-objects/
- https://www.sqlite.org/lockingv3.html
