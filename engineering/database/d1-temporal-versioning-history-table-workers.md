# D1 Temporal Versioning History Table Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to track every change made to a row over time — who changed it, when, and
what the previous values were — so that you can reconstruct the state of a record at
any past point, produce audit trails, support undo/restore, or power a "version
history" UI.  Simple `updated_at` timestamps only capture the moment of the last
change; a history table captures every change.

---

## Context

The pattern is called a **history table** (also: audit table, shadow table, temporal
table).  For every mutable row in a source table, every write produces a new row in
a parallel `_history` table stamped with `valid_from` and `valid_to` timestamps.
The current row in the source table is always the authoritative live version; the
history table is append-only.

SQLite (and D1) does not have `FOR SYSTEM TIME AS OF` syntax like PostgreSQL 18 or
SQL Server.  The reconstruction query is written by hand, but it is straightforward:
find the history row whose `valid_from <= t AND (valid_to IS NULL OR valid_to > t)`.

All writes must go through a helper that snapshots the old row into history and
updates the source row.  D1's `db.batch()` makes this atomic.

---

## Schema

```sql
-- migrations/0030_temporal_versioning.sql

CREATE TABLE IF NOT EXISTS products (
  id          TEXT    PRIMARY KEY,
  name        TEXT    NOT NULL,
  price_cents INTEGER NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'active',
  updated_by  TEXT    NOT NULL,
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
) STRICT;

-- History table: every past state of a product row.
CREATE TABLE IF NOT EXISTS products_history (
  history_id  INTEGER PRIMARY KEY,     -- ROWID alias; autoincrement
  product_id  TEXT    NOT NULL,
  name        TEXT    NOT NULL,
  price_cents INTEGER NOT NULL,
  status      TEXT    NOT NULL,
  changed_by  TEXT    NOT NULL,
  valid_from  INTEGER NOT NULL,        -- unixepoch() at time of change
  valid_to    INTEGER,                 -- NULL means "current at time of archive"
  change_type TEXT    NOT NULL         -- 'INSERT' | 'UPDATE' | 'DELETE'
) STRICT;

CREATE INDEX idx_ph_product_from ON products_history (product_id, valid_from);
CREATE INDEX idx_ph_product_to   ON products_history (product_id, valid_to);
```

---

## Core write helper

```typescript
// src/lib/temporal.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface ProductRow {
  id: string;
  name: string;
  price_cents: number;
  status: string;
  updated_by: string;
  updated_at: number;
}

export interface ProductUpdate {
  name?: string;
  price_cents?: number;
  status?: string;
}

/**
 * Update a product row and snapshot the old row into products_history
 * in a single atomic batch.  Returns the updated row or null if not found.
 */
export async function updateProduct(
  db: D1Database,
  id: string,
  patch: ProductUpdate,
  changedBy: string,
): Promise<ProductRow | null> {
  // 1. Read the current row first.
  const current = await db
    .prepare(`SELECT * FROM products WHERE id = ?1`)
    .bind(id)
    .first<ProductRow>();

  if (!current) return null;

  const now = Math.floor(Date.now() / 1000);

  // 2. Build the merged new row.
  const next: ProductRow = {
    ...current,
    ...patch,
    updated_by: changedBy,
    updated_at: now,
  };

  // 3. Snapshot old row into history, then update source — atomic batch.
  await db.batch([
    // Archive the old state.
    db
      .prepare(
        `INSERT INTO products_history
           (product_id, name, price_cents, status, changed_by, valid_from, valid_to, change_type)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 'UPDATE')`,
      )
      .bind(
        current.id,
        current.name,
        current.price_cents,
        current.status,
        current.updated_by,
        current.updated_at,
        now,                  // valid_to = now (the moment it became old)
      ),

    // Apply the new state.
    db
      .prepare(
        `UPDATE products
         SET name = ?1, price_cents = ?2, status = ?3,
             updated_by = ?4, updated_at = ?5
         WHERE id = ?6`,
      )
      .bind(next.name, next.price_cents, next.status, changedBy, now, id),
  ]);

  return next;
}

/** Insert a new product and record the initial INSERT in history. */
export async function createProduct(
  db: D1Database,
  product: Omit<ProductRow, 'updated_at'>,
): Promise<ProductRow> {
  const now = Math.floor(Date.now() / 1000);
  const row: ProductRow = { ...product, updated_at: now };

  await db.batch([
    db
      .prepare(
        `INSERT INTO products (id, name, price_cents, status, updated_by, updated_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
      )
      .bind(row.id, row.name, row.price_cents, row.status, row.updated_by, now),

    db
      .prepare(
        `INSERT INTO products_history
           (product_id, name, price_cents, status, changed_by, valid_from, valid_to, change_type)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, NULL, 'INSERT')`,
      )
      .bind(row.id, row.name, row.price_cents, row.status, row.updated_by, now),
  ]);

  return row;
}

/** Soft-delete: mark as deleted and archive the final state. */
export async function deleteProduct(
  db: D1Database,
  id: string,
  deletedBy: string,
): Promise<void> {
  const current = await db
    .prepare(`SELECT * FROM products WHERE id = ?1`)
    .bind(id)
    .first<ProductRow>();

  if (!current) return;

  const now = Math.floor(Date.now() / 1000);

  await db.batch([
    db
      .prepare(
        `INSERT INTO products_history
           (product_id, name, price_cents, status, changed_by, valid_from, valid_to, change_type)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 'DELETE')`,
      )
      .bind(current.id, current.name, current.price_cents, 'deleted',
            deletedBy, current.updated_at, now),

    db
      .prepare(`UPDATE products SET status = 'deleted', updated_by = ?1, updated_at = ?2 WHERE id = ?3`)
      .bind(deletedBy, now, id),
  ]);
}
```

---

## Point-in-time query: reconstruct row state at epoch T

```typescript
// src/lib/temporal.ts (continued)

export interface HistoryRow {
  product_id: string;
  name: string;
  price_cents: number;
  status: string;
  changed_by: string;
  valid_from: number;
  valid_to: number | null;
  change_type: string;
}

/**
 * Return what a product looked like at a given Unix timestamp.
 * Returns null if the product did not exist at that time.
 */
export async function productAsOf(
  db: D1Database,
  id: string,
  asOfUnix: number,
): Promise<HistoryRow | null> {
  // The history row whose validity window contains asOfUnix.
  return db
    .prepare(
      `SELECT *
       FROM   products_history
       WHERE  product_id = ?1
         AND  valid_from <= ?2
         AND  (valid_to IS NULL OR valid_to > ?2)
       ORDER  BY valid_from DESC
       LIMIT  1`,
    )
    .bind(id, asOfUnix)
    .first<HistoryRow>();
}

/** Return all history rows for an entity in chronological order. */
export async function productHistory(
  db: D1Database,
  id: string,
): Promise<HistoryRow[]> {
  const { results } = await db
    .prepare(
      `SELECT * FROM products_history
       WHERE product_id = ?1
       ORDER BY valid_from ASC`,
    )
    .bind(id)
    .all<HistoryRow>();
  return results;
}
```

---

## HTTP handler: history endpoint

```typescript
// src/handlers/product-handler.ts
import { productHistory, productAsOf } from '../lib/temporal';

export async function handleProductHistory(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);
  const id = url.pathname.split('/')[2]; // /products/:id/history
  const asOf = url.searchParams.get('as_of');

  if (asOf) {
    const ts = Number(asOf);
    if (!Number.isFinite(ts)) return new Response('Invalid as_of', { status: 400 });
    const row = await productAsOf(env.DB, id, ts);
    if (!row) return new Response('Not found at that time', { status: 404 });
    return Response.json(row);
  }

  const history = await productHistory(env.DB, id);
  return Response.json(history);
}
```

---

## Anti-patterns

- **Updating the history table** — history rows are immutable.  Any UPDATE or DELETE
  on `products_history` destroys the audit trail.  Grant only INSERT and SELECT on
  the history table to the Worker's D1 binding.

- **Relying on triggers for history writes** — SQLite triggers are per-connection.
  D1 does not guarantee trigger persistence across connections in the same way a
  long-lived Postgres server does.  Write history rows explicitly in the application
  layer with `db.batch()`.

- **Storing only diffs** — diff-based history (storing only changed fields) makes
  point-in-time reconstruction complex.  Full snapshots are simpler and usually
  acceptable for the row sizes involved in D1.

- **Not indexing `valid_from` / `valid_to`** — point-in-time queries without these
  indexes degrade to full scans of the history table as it grows.

---

## Gotchas

- `valid_to IS NULL` in the history table means "current at the time it was archived
  via DELETE" not "current live row".  The live row is always the source table; use
  history only for past states.

- Clock skew between Worker instances is rare but possible.  If two concurrent
  updates happen within the same second, `valid_from == valid_to` can produce a
  zero-width validity window.  Use millisecond-precision timestamps
  (`Date.now()` in ms) if sub-second change frequency is expected.

- History tables grow without bound.  Implement a retention policy: delete history
  rows older than your compliance window (e.g., 7 years for financial records, 90
  days for user activity).  Cascade deletes from the source table will not clean
  history if the source row is kept (soft-delete pattern).

- The `db.batch()` call is not literally a BEGIN/COMMIT transaction in the SQL sense;
  it is an atomic batch at the D1 API level.  If you need classical SQL transactions
  with rollback on application-logic errors, wrap the batch inside a
  `db.prepare('BEGIN')` / `db.prepare('COMMIT')` pattern.

---

## Verification

```typescript
import { describe, it, expect, beforeAll } from 'vitest';
import { env } from 'cloudflare:test';
import { createProduct, updateProduct, productAsOf, productHistory } from '../src/lib/temporal';

describe('temporal versioning', () => {
  beforeAll(async () => { /* apply migrations */ });

  it('records initial creation in history', async () => {
    await createProduct(env.DB, { id: 'p1', name: 'Widget', price_cents: 999, status: 'active', updated_by: 'alice' });
    const history = await productHistory(env.DB, 'p1');
    expect(history).toHaveLength(1);
    expect(history[0].change_type).toBe('INSERT');
  });

  it('preserves old state after update', async () => {
    const t0 = Math.floor(Date.now() / 1000) - 1;
    await updateProduct(env.DB, 'p1', { price_cents: 1299 }, 'bob');
    const snapshot = await productAsOf(env.DB, 'p1', t0);
    expect(snapshot?.price_cents).toBe(999);
  });

  it('reflects new state after update', async () => {
    const t1 = Math.floor(Date.now() / 1000) + 1;
    const snapshot = await productAsOf(env.DB, 'p1', t1);
    expect(snapshot?.price_cents).toBe(1299);
  });
});
```

---

## Related

- `d1-audit-event-log.md` — append-only event log for actions (who did what), distinct
  from full row snapshots.
- `d1-soft-delete-workers-middleware.md` — marking rows deleted without physical
  removal; pairs with history tables.
- `d1-optimistic-locking-version-column-workers.md` — version counters prevent
  concurrent overwrites; combine with history tables for a complete audit trail.
- `archive-table-patterns.md` — moving cold rows to a separate archive table rather
  than tracking every change.

---

## Sources

- SQL:2011 temporal tables standard overview: https://en.wikipedia.org/wiki/Temporal_database
- SQLite ROWID and autoincrement: https://www.sqlite.org/rowidtable.html
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- PostgreSQL temporal table pattern (conceptual reference): https://www.postgresql.org/docs/current/queries-table-expressions.html
