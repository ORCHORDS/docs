# Soft Delete Pattern with D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Deleting rows from a D1 table permanently makes audit trails impossible, breaks foreign-key references from audit logs, and prevents accidental-deletion recovery without a full database restore. Product and compliance requirements often demand that deleted records remain queryable for 30–90 days after deletion and that every deletion event is logged with who deleted what and when.

## Context

The soft-delete pattern marks rows as deleted with a `deleted_at` timestamp instead of removing them. Application queries filter out deleted rows transparently via SQLite views. A cleanup cron job performs the real `DELETE` after a configurable retention period. D1 (SQLite) supports views and computed columns but not stored procedures; business logic lives in the Worker or in trigger DDL. D1 does support `AFTER DELETE` and `AFTER UPDATE` triggers for side-effects like writing to an audit log table.

## Solution

```typescript
// src/db/soft-delete.ts
import type { D1Database } from '@cloudflare/workers-types';

// ----- Schema (run via migration) ------------------------------------------

export const SOFT_DELETE_SCHEMA_SQL = `
  CREATE TABLE IF NOT EXISTS records (
    id           TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL,
    payload      TEXT NOT NULL,           -- JSON blob
    created_at   INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at   INTEGER NOT NULL DEFAULT (unixepoch()),
    deleted_at   INTEGER,                 -- NULL = active, non-NULL = deleted
    deleted_by   TEXT                     -- user_id of deleter
  );

  -- Index: soft-delete filter is always present in WHERE clauses.
  -- Partial index on active rows avoids scanning deleted rows.
  CREATE INDEX IF NOT EXISTS idx_records_active
    ON records(owner_id, created_at)
    WHERE deleted_at IS NULL;

  -- Index on deleted_at for the cleanup cron.
  CREATE INDEX IF NOT EXISTS idx_records_deleted_at
    ON records(deleted_at)
    WHERE deleted_at IS NOT NULL;

  -- View: application code queries this view, not the base table.
  CREATE VIEW IF NOT EXISTS active_records AS
    SELECT id, owner_id, payload, created_at, updated_at
    FROM records
    WHERE deleted_at IS NULL;

  -- Audit log table.
  CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT    NOT NULL,
    record_id   TEXT    NOT NULL,
    action      TEXT    NOT NULL,   -- 'soft_delete' | 'hard_delete' | 'undelete'
    actor_id    TEXT,
    occurred_at INTEGER NOT NULL DEFAULT (unixepoch()),
    metadata    TEXT                -- JSON
  );

  CREATE INDEX IF NOT EXISTS idx_audit_record
    ON audit_log(table_name, record_id, occurred_at);

  -- Trigger: log to audit_log on soft delete (deleted_at goes NULL → non-NULL).
  CREATE TRIGGER IF NOT EXISTS trg_records_soft_delete
  AFTER UPDATE OF deleted_at ON records
  WHEN NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL
  BEGIN
    INSERT INTO audit_log (table_name, record_id, action, actor_id, metadata)
    VALUES (
      'records',
      NEW.id,
      'soft_delete',
      NEW.deleted_by,
      json_object('deleted_at', NEW.deleted_at)
    );
  END;

  -- Trigger: log when a soft-deleted row is hard-deleted by the cleanup cron.
  CREATE TRIGGER IF NOT EXISTS trg_records_hard_delete
  AFTER DELETE ON records
  WHEN OLD.deleted_at IS NOT NULL
  BEGIN
    INSERT INTO audit_log (table_name, record_id, action, actor_id, metadata)
    VALUES (
      'records',
      OLD.id,
      'hard_delete',
      NULL,
      json_object('originally_deleted_at', OLD.deleted_at)
    );
  END;
`;

// ----- Types ----------------------------------------------------------------

export interface ActiveRecord {
  id: string;
  owner_id: string;
  payload: string;
  created_at: number;
  updated_at: number;
}

export interface SoftDeleteOptions {
  actorId: string;
  /** Cascade soft-delete to child records in other tables */
  cascadeToChildren?: boolean;
}

// ----- CRUD helpers ---------------------------------------------------------

export async function createRecord(
  db: D1Database,
  ownerId: string,
  payload: unknown
): Promise<string> {
  const id = crypto.randomUUID();
  await db
    .prepare(
      `INSERT INTO records (id, owner_id, payload) VALUES (?, ?, ?)`
    )
    .bind(id, ownerId, JSON.stringify(payload))
    .run();
  return id;
}

export async function getActiveRecord(
  db: D1Database,
  id: string
): Promise<ActiveRecord | null> {
  // Query the view — automatically excludes soft-deleted rows.
  return db
    .prepare(`SELECT * FROM active_records WHERE id = ?`)
    .bind(id)
    .first<ActiveRecord>();
}

export async function softDeleteRecord(
  db: D1Database,
  id: string,
  options: SoftDeleteOptions
): Promise<boolean> {
  const { actorId, cascadeToChildren = false } = options;
  const now = Math.floor(Date.now() / 1000);

  const statements = [
    db
      .prepare(
        `UPDATE records
         SET deleted_at = ?, deleted_by = ?, updated_at = ?
         WHERE id = ? AND deleted_at IS NULL`
      )
      .bind(now, actorId, now, id),
  ];

  if (cascadeToChildren) {
    // Example: cascade to a child table with a foreign key.
    statements.push(
      db
        .prepare(
          `UPDATE record_items
           SET deleted_at = ?, updated_at = ?
           WHERE record_id = ? AND deleted_at IS NULL`
        )
        .bind(now, now, id)
    );
  }

  const results = await db.batch(statements);
  return (results[0].meta.changes ?? 0) > 0;
}

export async function undeleteRecord(
  db: D1Database,
  id: string,
  actorId: string
): Promise<boolean> {
  const now = Math.floor(Date.now() / 1000);
  const result = await db
    .prepare(
      `UPDATE records
       SET deleted_at = NULL, deleted_by = NULL, updated_at = ?
       WHERE id = ? AND deleted_at IS NOT NULL`
    )
    .bind(now, id)
    .run();

  if ((result.meta.changes ?? 0) > 0) {
    await db
      .prepare(
        `INSERT INTO audit_log (table_name, record_id, action, actor_id)
         VALUES ('records', ?, 'undelete', ?)`
      )
      .bind(id, actorId)
      .run();
    return true;
  }
  return false;
}

// ----- Cleanup cron (hard-delete after retention period) -------------------

export async function hardDeleteExpiredRecords(
  db: D1Database,
  retentionDays: number = 30
): Promise<number> {
  const cutoff = Math.floor(Date.now() / 1000) - retentionDays * 86400;

  // Delete in batches to avoid long-running transactions in D1.
  let totalDeleted = 0;
  let batchSize = 100;

  while (true) {
    const result = await db
      .prepare(
        `DELETE FROM records
         WHERE id IN (
           SELECT id FROM records
           WHERE deleted_at IS NOT NULL
             AND deleted_at < ?
           LIMIT ?
         )`
      )
      .bind(cutoff, batchSize)
      .run();

    const deleted = result.meta.changes ?? 0;
    totalDeleted += deleted;

    if (deleted < batchSize) break; // no more rows to delete
  }

  console.log(
    `[cleanup] hard-deleted ${totalDeleted} records older than ${retentionDays} days.`
  );
  return totalDeleted;
}

// ----- Worker entry point with cron ----------------------------------------

// src/index.ts
export interface Env {
  DB: D1Database;
  RETENTION_DAYS?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'DELETE' && url.pathname.startsWith('/records/')) {
      const id = url.pathname.split('/')[2];
      const actorId = request.headers.get('x-user-id') ?? 'anonymous';
      const deleted = await softDeleteRecord(env.DB, id, { actorId });
      return deleted
        ? new Response(null, { status: 204 })
        : new Response('Not Found', { status: 404 });
    }

    if (request.method === 'POST' && url.pathname.endsWith('/undelete')) {
      const id = url.pathname.split('/')[2];
      const actorId = request.headers.get('x-user-id') ?? 'anonymous';
      const ok = await undeleteRecord(env.DB, id, actorId);
      return ok
        ? Response.json({ restored: true })
        : new Response('Not Found or Already Active', { status: 404 });
    }

    return new Response('Not Found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const retentionDays = parseInt(env.RETENTION_DAYS ?? '30', 10);
    await hardDeleteExpiredRecords(env.DB, retentionDays);
  },
};
```

## Implementation Details

**Partial indexes** — `CREATE INDEX ... WHERE deleted_at IS NULL` creates an index over only active rows. Most application queries filter on `deleted_at IS NULL`; this partial index is smaller and faster than a full-table index.

**SQLite view for application code** — `active_records` view removes the need for every query to repeat `WHERE deleted_at IS NULL`. Application code that queries `records` directly bypasses the soft-delete filter, which is only safe for admin or audit APIs.

**Atomic batch** — `softDeleteRecord` uses `db.batch()` to cascade the soft-delete to child tables in a single HTTP round-trip. All statements in a D1 batch execute atomically.

**Batched hard-delete** — deleting thousands of rows in a single SQL statement can exceed D1's per-request duration limit. The `while` loop deletes 100 rows at a time and terminates when fewer rows are deleted than the batch size.

**Trigger-based audit log** — the `AFTER UPDATE OF deleted_at` trigger fires only when `deleted_at` changes from NULL to non-NULL. This avoids logging updates to other columns. The hard-delete trigger similarly captures the cleanup event.

## Anti-patterns

- **Filtering with `deleted_at = NULL`** — use `IS NULL`, not `= NULL`; SQL NULL comparisons with `=` always evaluate to NULL (falsy).
- **Omitting the partial index** — a full-table index on `deleted_at` wastes space and is slower for the common `IS NULL` case.
- **Soft-deleting without cascading** — child rows with foreign keys to soft-deleted parents become orphans. Always cascade.
- **No retention policy** — without a hard-delete cron, the table grows indefinitely and query performance degrades.
- **Querying the base table from application code** — bypasses the view, allowing deleted rows to appear in API responses.

## Gotchas

- D1 views are read-only. `INSERT`, `UPDATE`, and `DELETE` against `active_records` will fail; write to the `records` base table.
- The `WHEN` clause on triggers uses `NEW` and `OLD` pseudo-tables. Ensure the trigger `WHEN` condition matches the exact transition you care about.
- D1's cron `scheduled()` handler has a 30-second CPU time limit. Keep each batch small (100–500 rows) to stay within budget.
- `result.meta.changes` returns the number of rows affected by the last statement in a batch, not the total. Check `results[0].meta.changes` for the first statement.
- Undeleting a row does not automatically undelete its cascaded children. Implement `undeleteRecordItems` if cascade-undelete is required.

## Verification

```typescript
// Integration test sketch
async function verify(db: D1Database) {
  const id = await createRecord(db, 'user-1', { name: 'test' });

  // Row is visible via active_records view.
  const before = await getActiveRecord(db, id);
  console.assert(before !== null, 'record is active');

  // Soft-delete.
  await softDeleteRecord(db, id, { actorId: 'user-1' });
  const afterDelete = await getActiveRecord(db, id);
  console.assert(afterDelete === null, 'record hidden after soft-delete');

  // Audit log entry exists.
  const audit = await db
    .prepare(`SELECT * FROM audit_log WHERE record_id = ? AND action = 'soft_delete'`)
    .bind(id)
    .first();
  console.assert(audit !== null, 'audit log entry created');

  // Undelete.
  await undeleteRecord(db, id, 'admin');
  const afterUndelete = await getActiveRecord(db, id);
  console.assert(afterUndelete !== null, 'record visible after undelete');
}
```

## Related

- [workers-d1-schema-versioning](workers-d1-schema-versioning.md)
- [workers-d1-full-text-search](workers-d1-full-text-search.md)
- [workers-d1-time-series-data](workers-d1-time-series-data.md)

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/partialindex.html
- https://www.sqlite.org/lang_createtrigger.html
- https://www.sqlite.org/lang_createview.html
