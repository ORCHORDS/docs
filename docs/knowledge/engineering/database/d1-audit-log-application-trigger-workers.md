# Application-Layer Audit Logging in D1 (Cloudflare Workers)

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a complete change history for sensitive rows (orders, user profiles, billing records) so that support staff can answer "who changed this and when?". D1 is built on SQLite and does not support SQL-level triggers, so audit rows must be written from application code.

## Context

SQLite triggers exist in the engine but D1 does not expose DDL for creating them. All mutating operations — INSERT, UPDATE, DELETE — must therefore be routed through an application helper that writes to an `audit_log` table atomically with the data change. D1's `batch()` API executes multiple statements in one round trip and within a single implicit transaction, which is the key to atomicity here.

---

## Schema

```sql
CREATE TABLE IF NOT EXISTS audit_log (
  id          TEXT    PRIMARY KEY,   -- UUID v4
  table_name  TEXT    NOT NULL,
  row_id      TEXT    NOT NULL,
  action      TEXT    NOT NULL CHECK (action IN ('INSERT','UPDATE','DELETE')),
  old_value   TEXT,                  -- JSON snapshot before change, NULL on INSERT
  new_value   TEXT,                  -- JSON snapshot after change, NULL on DELETE
  user_id     TEXT,
  logged_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_audit_row  ON audit_log (table_name, row_id, logged_at DESC);
CREATE INDEX idx_audit_user ON audit_log (user_id, logged_at DESC);
```

## Audit Helper and Batch Write

```typescript
// src/db/audit.ts
import type { D1Database, D1PreparedStatement } from '@cloudflare/workers-types';
import { randomUUID } from 'crypto';

export type AuditAction = 'INSERT' | 'UPDATE' | 'DELETE';

/**
 * Build a prepared statement that inserts one audit row.
 * Call this alongside your data mutation inside db.batch([...]).
 */
export function buildAuditStmt(
  db: D1Database,
  table: string,
  rowId: string,
  action: AuditAction,
  oldValue: unknown,
  newValue: unknown,
  userId: string | null,
): D1PreparedStatement {
  return db
    .prepare(
      `INSERT INTO audit_log (id, table_name, row_id, action, old_value, new_value, user_id)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      randomUUID(),
      table,
      rowId,
      action,
      oldValue != null ? JSON.stringify(oldValue) : null,
      newValue != null ? JSON.stringify(newValue) : null,
      userId,
    );
}

// src/db/orders.ts
import type { D1Database } from '@cloudflare/workers-types';
import { buildAuditStmt } from './audit';

export interface Order {
  id: string;
  user_id: string;
  status: string;
  total_cents: number;
}

/** Update order status and write an audit row atomically. */
export async function updateOrderStatus(
  db: D1Database,
  orderId: string,
  newStatus: string,
  actingUserId: string,
): Promise<void> {
  // 1. Read current state for old_value snapshot
  const old = await db
    .prepare(`SELECT * FROM orders WHERE id = ?`)
    .bind(orderId)
    .first<Order>();

  if (!old) throw new Error(`Order ${orderId} not found`);

  const updated: Order = { ...old, status: newStatus };

  // 2. Batch: data mutation + audit row in one implicit transaction
  await db.batch([
    db
      .prepare(`UPDATE orders SET status = ? WHERE id = ?`)
      .bind(newStatus, orderId),
    buildAuditStmt(db, 'orders', orderId, 'UPDATE', old, updated, actingUserId),
  ]);
}

/** Insert a new order and log the creation. */
export async function createOrder(
  db: D1Database,
  order: Omit<Order, 'id'>,
  actingUserId: string,
): Promise<string> {
  const id = randomUUID();
  const newOrder: Order = { id, ...order };

  await db.batch([
    db
      .prepare(
        `INSERT INTO orders (id, user_id, status, total_cents) VALUES (?, ?, ?, ?)`,
      )
      .bind(id, order.user_id, order.status, order.total_cents),
    buildAuditStmt(db, 'orders', id, 'INSERT', null, newOrder, actingUserId),
  ]);

  return id;
}

/** Soft-delete (or hard-delete) an order and log the removal. */
export async function deleteOrder(
  db: D1Database,
  orderId: string,
  actingUserId: string,
): Promise<void> {
  const old = await db
    .prepare(`SELECT * FROM orders WHERE id = ?`)
    .bind(orderId)
    .first<Order>();

  if (!old) return;

  await db.batch([
    db.prepare(`DELETE FROM orders WHERE id = ?`).bind(orderId),
    buildAuditStmt(db, 'orders', orderId, 'DELETE', old, null, actingUserId),
  ]);
}
```

## Query Endpoint — Audit History for a Row

```typescript
// src/handlers/auditHistory.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface AuditEntry {
  id: string;
  action: string;
  old_value: string | null;
  new_value: string | null;
  user_id: string | null;
  logged_at: string;
}

export async function getAuditHistory(
  db: D1Database,
  table: string,
  rowId: string,
  limit = 50,
): Promise<AuditEntry[]> {
  const { results } = await db
    .prepare(
      `SELECT id, action, old_value, new_value, user_id, logged_at
       FROM audit_log
       WHERE table_name = ? AND row_id = ?
       ORDER BY logged_at DESC
       LIMIT ?`,
    )
    .bind(table, rowId, limit)
    .all<AuditEntry>();
  return results;
}
```

## Anti-patterns

- **Writing the audit row in a separate `await` outside `batch()`.** If the data mutation succeeds but the audit insert fails (or vice versa), you get a silent inconsistency. Always use `db.batch([dataMutation, auditStmt])`.
- **Storing only a diff instead of full snapshots.** Diffs are harder to reason about when you need to reconstruct state at a point in time. Full JSON snapshots are cheaper to store in D1 than the engineering time to implement reliable diffing.
- **Omitting `user_id`.** Machine-initiated changes (cron jobs, background workers) should still record an actor identifier such as `'system:purge-job'`.
- **Logging reads.** Audit tables should record mutations only. High-volume SELECT logging floods the table and masks meaningful events.

## Gotchas

- D1 `batch()` runs statements in order within an implicit transaction but does not roll back automatically on a partial failure in the current D1 beta behaviour — verify this against the latest D1 documentation for your plan tier.
- `randomUUID()` is available in the Workers runtime without importing the Node.js `crypto` module — it is a global. If bundling for Node.js compatibility mode, import from `'node:crypto'`.
- `old_value` and `new_value` are stored as JSON strings. Parse them before diffing: `JSON.parse(entry.old_value ?? 'null')`.
- The `audit_log` table can grow large. Implement a retention policy (e.g. DELETE rows older than 1 year) as a separate Cron Trigger.

## Verification

```sql
-- View the last 10 changes to a specific order
SELECT action, user_id, logged_at, old_value, new_value
FROM audit_log
WHERE table_name = 'orders' AND row_id = 'order-uuid-here'
ORDER BY logged_at DESC
LIMIT 10;

-- Count audit rows by action type
SELECT action, COUNT(*) FROM audit_log GROUP BY action;

-- Find all changes made by a specific user in the last 7 days
SELECT table_name, row_id, action, logged_at
FROM audit_log
WHERE user_id = 'user-uuid-here'
  AND logged_at >= datetime('now', '-7 days')
ORDER BY logged_at DESC;
```

## Related

- `d1-soft-delete-pattern-workers.md` — combine soft-delete with audit logging
- `d1-json-column-query-workers.md` — query the JSON snapshots stored in audit rows
- Cloudflare D1 `batch()` API documentation

## Sources

- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/lang_createtrigger.html (D1 does not expose this DDL)
