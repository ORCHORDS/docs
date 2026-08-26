# D1 Audit Shadow Table Trigger Pattern in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a row-level audit trail that captures the *before* and *after* state of every UPDATE and DELETE without modifying application code. The shadow-table pattern keeps a mirror table of historic row versions written by SQLite triggers, giving you point-in-time reconstruction and compliance-grade change history.

## Context

D1 supports `AFTER UPDATE` and `AFTER DELETE` triggers. A shadow table mirrors the production table's columns and adds audit metadata: `_op TEXT`, `_changed_at TEXT`, `_changed_by TEXT`. Triggers copy the OLD row into the shadow table before the mutation is committed. This is distinct from a CDC log (which records events) and from an append-only event-source table (which records intentions) — a shadow table records the *superseded state* exactly.

---

## Schema: Production and Shadow Tables

```sql
-- Production table
CREATE TABLE IF NOT EXISTS products (
  id          INTEGER PRIMARY KEY,
  sku         TEXT    NOT NULL UNIQUE,
  price_cents INTEGER NOT NULL,
  stock       INTEGER NOT NULL DEFAULT 0,
  updated_by  TEXT,
  updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Shadow table: identical columns plus audit envelope
CREATE TABLE IF NOT EXISTS products_shadow (
  _shadow_id   INTEGER PRIMARY KEY,
  _op          TEXT NOT NULL CHECK (_op IN ('UPDATE','DELETE')),
  _changed_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  _changed_by  TEXT,
  -- mirrored payload
  id          INTEGER NOT NULL,
  sku         TEXT    NOT NULL,
  price_cents INTEGER NOT NULL,
  stock       INTEGER NOT NULL,
  updated_by  TEXT,
  updated_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shadow_id_op ON products_shadow (id, _changed_at DESC);
```

---

## Triggers

```sql
-- Capture superseded row before UPDATE
CREATE TRIGGER IF NOT EXISTS trg_products_before_update
AFTER UPDATE ON products
FOR EACH ROW
BEGIN
  INSERT INTO products_shadow
    (_op, _changed_by, id, sku, price_cents, stock, updated_by, updated_at)
  VALUES
    ('UPDATE', OLD.updated_by, OLD.id, OLD.sku, OLD.price_cents,
     OLD.stock, OLD.updated_by, OLD.updated_at);
END;

-- Capture deleted row
CREATE TRIGGER IF NOT EXISTS trg_products_before_delete
AFTER DELETE ON products
FOR EACH ROW
BEGIN
  INSERT INTO products_shadow
    (_op, _changed_by, id, sku, price_cents, stock, updated_by, updated_at)
  VALUES
    ('DELETE', OLD.updated_by, OLD.id, OLD.sku, OLD.price_cents,
     OLD.stock, OLD.updated_by, OLD.updated_at);
END;
```

---

## Applying Migrations via Wrangler

```typescript
// migrations/0002_shadow_table.sql — committed to source control
// wrangler d1 migrations apply MY_DB --env production
// Wrangler executes the CREATE TABLE and CREATE TRIGGER statements in order.
```

Verify triggers were created:

```typescript
// worker-admin.ts
export async function listTriggers(db: D1Database): Promise<string[]> {
  const rows = await db
    .prepare("SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'products'")
    .all<{ name: string }>();
  return rows.results.map(r => r.name);
}
```

---

## Querying the Audit Trail

```typescript
// audit.ts
export interface AuditEntry {
  _shadow_id: number;
  _op: string;
  _changed_at: string;
  _changed_by: string | null;
  id: number;
  sku: string;
  price_cents: number;
  stock: number;
}

// Full history for a product row, newest first
export async function getProductHistory(
  db: D1Database,
  productId: number,
  limit = 50
): Promise<AuditEntry[]> {
  const rows = await db
    .prepare(
      `SELECT * FROM products_shadow
        WHERE id = ?
        ORDER BY _changed_at DESC
        LIMIT ?`
    )
    .bind(productId, limit)
    .all<AuditEntry>();
  return rows.results;
}

// Point-in-time reconstruction: what did the row look like before a given timestamp?
export async function getProductAt(
  db: D1Database,
  productId: number,
  asOf: string
): Promise<AuditEntry | null> {
  return db
    .prepare(
      `SELECT * FROM products_shadow
        WHERE id = ?
          AND _changed_at <= ?
        ORDER BY _changed_at DESC
        LIMIT 1`
    )
    .bind(productId, asOf)
    .first<AuditEntry>();
}
```

---

## Shadow Table Cleanup with Retention Policy

```typescript
// cron-purge.ts — registered as a Cron Trigger
export async function purgeShadowRows(db: D1Database, retainDays = 90): Promise<number> {
  const cutoff = new Date(Date.now() - retainDays * 86_400_000).toISOString();
  const result = await db
    .prepare('DELETE FROM products_shadow WHERE _changed_at < ?')
    .bind(cutoff)
    .run();
  return result.meta.changes;
}
```

---

## Anti-patterns

- **Putting triggers on high-frequency write tables without a retention policy** — shadow tables grow without bound; always pair with a purge Cron Trigger.
- **Relying on `BEFORE` triggers in SQLite** — SQLite `BEFORE` triggers fire before the row is modified and do not see the final committed values for `NEW`; always use `AFTER` triggers for audit purposes.
- **Storing the `_changed_by` from a session variable** — D1 has no session context; pass the actor ID as a column on the production table (`updated_by`) so triggers can copy it from `OLD`.
- **Omitting the index on `(id, _changed_at DESC)`** — history queries scan the entire shadow table without this index.

## Gotchas

- Triggers fire inside the same transaction as the originating DML; if the transaction rolls back, the shadow row is also rolled back — giving you a consistent audit trail automatically.
- D1 does not support `CREATE TRIGGER … INSTEAD OF` on base tables (only on views); all shadow-table triggers must be `AFTER`.
- Adding a new column to the production table requires a corresponding `ALTER TABLE products_shadow ADD COLUMN` migration *and* updating both trigger definitions — test in a preview D1 database first.
- `_changed_at` uses SQLite's `strftime('%Y-%m-%dT%H:%M:%fZ','now')` which produces UTC ISO-8601 with milliseconds; do not use `CURRENT_TIMESTAMP` (it omits milliseconds and the trailing `Z`).

## Verification

```typescript
async function smokeTest(db: D1Database): Promise<void> {
  // Insert, update, delete
  await db.prepare("INSERT INTO products (id,sku,price_cents,stock,updated_by) VALUES (99,'TEST',1000,5,'admin')").run();
  await db.prepare("UPDATE products SET price_cents=1200, updated_by='alice' WHERE id=99").run();
  await db.prepare("DELETE FROM products WHERE id=99").run();

  const { getProductHistory } = await import('./audit');
  const history = await getProductHistory(db, 99);

  console.assert(history.length === 2, 'Expected 2 shadow rows (update + delete)');
  console.assert(history[0]._op === 'DELETE', 'Newest entry should be DELETE');
  console.assert(history[1]._op === 'UPDATE', 'Second entry should be UPDATE');
  console.assert(history[1].price_cents === 1000, 'Pre-update price should be captured');
}
```

## Related

- `d1-audit-event-log.md`
- `d1-cdc-change-tracking-triggers.md`
- `d1-triggers-data-validation-workers.md`
- `d1-temporal-versioning-history-table-workers.md`
- `d1-soft-delete-workers-middleware.md`

## Sources

- Cloudflare D1 triggers: https://developers.cloudflare.com/d1/
- SQLite trigger documentation: https://www.sqlite.org/lang_createtrigger.html
- Audit trail design patterns: https://martinfowler.com/eaaDev/AuditLog.html
