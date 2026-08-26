# Soft Delete and Restore Pattern in Cloudflare D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application needs to let users delete records without immediately destroying the data — for undo support, audit trails, or a grace period before permanent removal. Hard deletes lose data permanently and complicate recovery; soft deletes keep the row while hiding it from normal queries, and a scheduled Cron Trigger handles the eventual hard delete.

---

## Context

The soft delete pattern adds a nullable `deleted_at` timestamp column to the table. All application queries include `WHERE deleted_at IS NULL` so deleted rows are invisible by default. A SQLite view encapsulates this filter, letting existing queries target the view without modification. A `RESTORE` endpoint sets `deleted_at = NULL` to bring a row back. A Cloudflare Cron Trigger fires periodically and hard-deletes any row where `deleted_at` is older than the retention window (30 days). An admin endpoint allows listing soft-deleted rows for support tooling. Indexes on `deleted_at` keep the `IS NULL` filter and the Cron purge query efficient.

---

## Schema — Table, View & Indexes

```sql
CREATE TABLE IF NOT EXISTS documents (
  id          TEXT      PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id     TEXT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title       TEXT      NOT NULL,
  content     TEXT      NOT NULL DEFAULT '',
  deleted_at  DATETIME  DEFAULT NULL,   -- NULL = active, non-NULL = soft-deleted
  created_at  DATETIME  NOT NULL DEFAULT (datetime('now')),
  updated_at  DATETIME  NOT NULL DEFAULT (datetime('now'))
);

-- Partial index: keeps the "active" rows hot for standard queries.
CREATE INDEX IF NOT EXISTS idx_documents_active
  ON documents (user_id, created_at DESC)
  WHERE deleted_at IS NULL;

-- Index used by the Cron purge query and admin restore listing.
CREATE INDEX IF NOT EXISTS idx_documents_deleted_at
  ON documents (deleted_at)
  WHERE deleted_at IS NOT NULL;

-- View: application queries target this view — no filter needed at call site.
CREATE VIEW IF NOT EXISTS active_documents AS
  SELECT id, user_id, title, content, created_at, updated_at
  FROM   documents
  WHERE  deleted_at IS NULL;
```

---

## Implementation

```typescript
// src/lib/documents.ts
export interface Document {
  id: string;
  user_id: string;
  title: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface SoftDeletedDocument extends Document {
  deleted_at: string;
}

/** List active documents for a user (queries the view). */
export async function listDocuments(
  db: D1Database,
  userId: string,
  limit = 50
): Promise<Document[]> {
  const { results } = await db
    .prepare(
      `SELECT * FROM active_documents
       WHERE  user_id = ?
       ORDER  BY created_at DESC
       LIMIT  ?`
    )
    .bind(userId, limit)
    .all<Document>();
  return results;
}

/** Soft-delete a document: stamp deleted_at. */
export async function softDeleteDocument(
  db: D1Database,
  id: string,
  userId: string  // ownership check
): Promise<boolean> {
  const { meta } = await db
    .prepare(
      `UPDATE documents
       SET    deleted_at = datetime('now'),
              updated_at = datetime('now')
       WHERE  id = ?
         AND  user_id = ?
         AND  deleted_at IS NULL`  // idempotent: cannot double-delete
    )
    .bind(id, userId)
    .run();
  return (meta.changes ?? 0) > 0;
}

/** Restore a soft-deleted document: clear deleted_at. */
export async function restoreDocument(
  db: D1Database,
  id: string,
  userId: string
): Promise<Document | null> {
  const { results } = await db
    .prepare(
      `UPDATE documents
       SET    deleted_at = NULL,
              updated_at = datetime('now')
       WHERE  id = ?
         AND  user_id = ?
         AND  deleted_at IS NOT NULL
       RETURNING id, user_id, title, content, created_at, updated_at`
    )
    .bind(id, userId)
    .all<Document>();
  return results[0] ?? null;
}

/**
 * Admin: list soft-deleted documents across all users.
 * Ordered by deletion time so oldest candidates for purge appear first.
 */
export async function listSoftDeleted(
  db: D1Database,
  limit = 100
): Promise<SoftDeletedDocument[]> {
  const { results } = await db
    .prepare(
      `SELECT id, user_id, title, content, created_at, updated_at, deleted_at
       FROM   documents
       WHERE  deleted_at IS NOT NULL
       ORDER  BY deleted_at ASC
       LIMIT  ?`
    )
    .bind(limit)
    .all<SoftDeletedDocument>();
  return results;
}

/**
 * Cron job: permanently delete rows soft-deleted more than 30 days ago.
 * Returns the number of rows purged.
 */
export async function purgeSoftDeleted(
  db: D1Database,
  retentionDays = 30
): Promise<number> {
  const { meta } = await db
    .prepare(
      `DELETE FROM documents
       WHERE deleted_at IS NOT NULL
         AND deleted_at < datetime('now', ?)`
    )
    .bind(`-${retentionDays} days`)
    .run();
  return meta.changes ?? 0;
}
```

```typescript
// src/index.ts — Hono routes + Cron Trigger handler
import { Hono } from 'hono';
import {
  listDocuments,
  softDeleteDocument,
  restoreDocument,
  listSoftDeleted,
  purgeSoftDeleted,
} from './lib/documents';

type Env = { Bindings: { DB: D1Database } };

const app = new Hono<Env>();

// Standard CRUD: always queries active_documents view
app.get('/path/to/documents', async (c) => {
  const docs = await listDocuments(c.env.DB, c.req.param('userId'));
  return c.json(docs);
});

// Soft delete
app.delete('/documents/:id', async (c) => {
  // In production, derive userId from the auth token
  const userId = c.req.header('x-user-id') ?? '';
  const deleted = await softDeleteDocument(c.env.DB, c.req.param('id'), userId);
  return deleted ? c.json({ deleted: true }) : c.json({ error: 'not found' }, 404);
});

// Restore
app.post('/documents/:id/restore', async (c) => {
  const userId = c.req.header('x-user-id') ?? '';
  const doc = await restoreDocument(c.env.DB, c.req.param('id'), userId);
  return doc ? c.json(doc) : c.json({ error: 'not found or not deleted' }, 404);
});

// Admin: list soft-deleted
app.get('/admin/documents/deleted', async (c) => {
  const rows = await listSoftDeleted(c.env.DB);
  return c.json(rows);
});

// Cron Trigger scheduled handler (wrangler.toml: crons = ["0 3 * * *"])
export default {
  fetch: app.fetch,
  async scheduled(event: ScheduledEvent, env: Env['Bindings']): Promise<void> {
    const purged = await purgeSoftDeleted(env.DB, 30);
    console.log(`[cron] purged ${purged} expired soft-deleted documents`);
  },
};
```

```toml
# wrangler.toml (relevant section)
[triggers]
crons = ["0 3 * * *"]  # 03:00 UTC daily
```

---

## Testing / Verification

```typescript
// src/lib/documents.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { env } from 'cloudflare:test';
import {
  listDocuments,
  softDeleteDocument,
  restoreDocument,
  listSoftDeleted,
  purgeSoftDeleted,
} from './documents';

describe('Soft delete pattern', () => {
  const userId = 'u1';

  beforeEach(async () => {
    await env.DB.exec(`DELETE FROM documents`);
    await env.DB.exec(`
      INSERT INTO documents (id, user_id, title) VALUES
        ('d1', '${userId}', 'Alpha'),
        ('d2', '${userId}', 'Beta'),
        ('d3', '${userId}', 'Gamma');
    `);
  });

  it('lists only active documents', async () => {
    await softDeleteDocument(env.DB, 'd2', userId);
    const docs = await listDocuments(env.DB, userId);
    expect(docs.map(d => d.id)).toEqual(['d1', 'd3'].sort());
  });

  it('restore makes document visible again', async () => {
    await softDeleteDocument(env.DB, 'd1', userId);
    const restored = await restoreDocument(env.DB, 'd1', userId);
    expect(restored).not.toBeNull();
    const docs = await listDocuments(env.DB, userId);
    expect(docs.some(d => d.id === 'd1')).toBe(true);
  });

  it('lists soft-deleted documents in admin view', async () => {
    await softDeleteDocument(env.DB, 'd3', userId);
    const deleted = await listSoftDeleted(env.DB);
    expect(deleted.some(d => d.id === 'd3')).toBe(true);
    expect(deleted[0].deleted_at).toBeTruthy();
  });

  it('purge removes only expired rows', async () => {
    await env.DB.exec(`
      UPDATE documents
      SET deleted_at = datetime('now', '-31 days')
      WHERE id = 'd1';
      UPDATE documents
      SET deleted_at = datetime('now', '-1 day')
      WHERE id = 'd2';
    `);
    const purged = await purgeSoftDeleted(env.DB, 30);
    expect(purged).toBe(1);  // only d1 is old enough
    const { results } = await env.DB
      .prepare(`SELECT id FROM documents WHERE deleted_at IS NOT NULL`)
      .all<{ id: string }>();
    expect(results.map(r => r.id)).toEqual(['d2']);
  });
});
```

---

## Anti-patterns

- **Forgetting `WHERE deleted_at IS NULL` in every query** — instead of repeating the filter, point application code at the `active_documents` view; the filter lives in one place.
- **Using a boolean `is_deleted` column** — a boolean carries no temporal information; you lose the ability to purge by age or show deletion timestamps in the admin UI.
- **Cascading hard-deletes on parent delete** — if a parent row is hard-deleted via `ON DELETE CASCADE`, child rows with `deleted_at` set will also disappear, bypassing the retention window. Handle parent deletes explicitly or use soft deletes on parent tables too.
- **Purging in a single unbounded DELETE** — on large tables a single `DELETE … WHERE deleted_at < ?` can lock the table for seconds. Batch the purge: `DELETE FROM documents WHERE id IN (SELECT id FROM documents WHERE deleted_at < ? LIMIT 500)`.

---

## Gotchas

- SQLite partial indexes (`WHERE deleted_at IS NULL`) are not used by queries that omit the same predicate; the standard index `idx_documents_deleted_at` is used by the purge query.
- `meta.changes` is `0` if the `WHERE` clause matches no row — check this to distinguish "not found" from "already deleted" in your HTTP response.
- The `active_documents` view excludes `deleted_at` — if you need to expose deletion timestamps to an API caller, query the base table directly.
- Restoring a row does not reset `updated_at` to the pre-deletion value; it gets the current timestamp. If you need to preserve `updated_at` through delete/restore, store it separately.
- The Cron Trigger runs at most once per minute (Cloudflare limit) and is not guaranteed to fire at exactly the scheduled second; use `datetime('now', '-30 days')` rather than a client-computed timestamp to avoid clock skew.

---

## Verification

```bash
# Confirm active_documents view excludes soft-deleted rows
wrangler d1 execute orchords-db --command "
  UPDATE documents SET deleted_at = datetime('now') WHERE id = 'SOME_ID';
  SELECT COUNT(*) AS visible FROM active_documents;
  SELECT COUNT(*) AS total   FROM documents;
"

# Test Cron Trigger locally
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+3+*+*+*"

# Check purge candidate count
wrangler d1 execute orchords-db --command "
  SELECT COUNT(*) FROM documents
  WHERE deleted_at IS NOT NULL
    AND deleted_at < datetime('now', '-30 days');
"
```

---

## Related

- `d1-cursor-pagination-keyset.md`
- `d1-upsert-conflict-resolution.md`
- `d1-read-replica-binding.md`

---

## Sources

- Cloudflare D1 Docs — https://developers.cloudflare.com/d1/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- SQLite Partial Indexes — https://www.sqlite.org/partialindex.html
