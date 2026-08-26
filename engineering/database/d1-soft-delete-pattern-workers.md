# D1 Soft Delete Pattern in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to let users "delete" records without permanently removing them from the database. Deleted rows must be hidden from all normal queries but remain recoverable for auditing, undo, or compliance retention windows.

## Context

D1 is Cloudflare's edge-native SQLite database. SQLite does not support partial indexes in the same sense as PostgreSQL, but it does support `WHERE` clauses on `CREATE INDEX`, which is the key to keeping soft-delete performant. The pattern adds a single nullable `deleted_at TEXT` column (ISO-8601 timestamp stored as text, which SQLite sorts correctly) and wraps all data access behind a filter on that column.

---

## Schema and Index Strategy

```sql
-- Migration: add soft-delete support to an existing table
ALTER TABLE items ADD COLUMN deleted_at TEXT DEFAULT NULL;

-- Partial index: only indexes rows that ARE soft-deleted.
-- All live-data queries (WHERE deleted_at IS NULL) skip this index
-- entirely via the SQLite query planner, keeping their own scans fast.
-- Recycle / purge queries (WHERE deleted_at IS NOT NULL) use it.
CREATE INDEX idx_items_deleted
  ON items (deleted_at)
  WHERE deleted_at IS NOT NULL;

-- Optional: composite index if you frequently query by user + live status
CREATE INDEX idx_items_user_live
  ON items (user_id, created_at DESC)
  WHERE deleted_at IS NULL;
```

```typescript
// src/db/items.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface Item {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  deleted_at: string | null;
}

/** Return all live items for a user (soft-deleted rows excluded). */
export async function listItems(
  db: D1Database,
  userId: string,
): Promise<Item[]> {
  const { results } = await db
    .prepare(
      `SELECT id, user_id, title, created_at
       FROM items
       WHERE user_id = ? AND deleted_at IS NULL
       ORDER BY created_at DESC`,
    )
    .bind(userId)
    .all<Item>();
  return results;
}

/** Fetch a single live item; returns null if missing or soft-deleted. */
export async function getItem(
  db: D1Database,
  id: string,
): Promise<Item | null> {
  return db
    .prepare(
      `SELECT * FROM items WHERE id = ? AND deleted_at IS NULL`,
    )
    .bind(id)
    .first<Item>();
}

/** Soft-delete: stamp deleted_at, do not remove the row. */
export async function softDelete(
  db: D1Database,
  id: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE items SET deleted_at = datetime('now') WHERE id = ? AND deleted_at IS NULL`,
    )
    .bind(id)
    .run();
}

/** Hard-delete all rows soft-deleted more than 90 days ago.
 *  Intended to be called from a Cron Trigger Worker. */
export async function purgeExpired(db: D1Database): Promise<number> {
  const result = await db
    .prepare(
      `DELETE FROM items
       WHERE deleted_at IS NOT NULL
         AND deleted_at < datetime('now', '-90 days')`,
    )
    .run();
  return result.meta.changes;
}
```

```typescript
// src/cron.ts — Cloudflare Cron Trigger handler
import { purgeExpired } from './db/items';

export default {
  async scheduled(
    _event: ScheduledEvent,
    env: Env,
    _ctx: ExecutionContext,
  ): Promise<void> {
    const removed = await purgeExpired(env.DB);
    console.log(`Purged ${removed} expired soft-deleted rows`);
  },
};
```

```toml
# wrangler.toml — wire up the daily purge cron
[triggers]
crons = ["0 3 * * *"]   # 03:00 UTC every day
```

## Restore / Undelete

```typescript
export async function restoreItem(
  db: D1Database,
  id: string,
): Promise<void> {
  await db
    .prepare(
      `UPDATE items SET deleted_at = NULL WHERE id = ?`,
    )
    .bind(id)
    .run();
}
```

Always check ownership before restoring — a user should only be able to restore their own records.

## Anti-patterns

- **Forgetting the filter in joins.** Any query that joins `items` to another table must also carry `items.deleted_at IS NULL`, or soft-deleted rows will silently appear in joined result sets.
- **Using a boolean `is_deleted` column.** A boolean gives you no recovery window information. `deleted_at TEXT` is strictly better: it enables time-based purge crons and surfaces deletion timing in audit queries.
- **Indexing `deleted_at` unconditionally.** A full index on a column that is NULL for 99 % of rows wastes page space. The `WHERE deleted_at IS NOT NULL` partial index costs almost nothing for live-data scans while still accelerating the purge cron.
- **Not testing the purge in staging.** The `purgeExpired` function performs a bulk DELETE. Validate row counts with a SELECT before running against production.

## Gotchas

- `datetime('now')` in SQLite returns UTC. If your application stores timestamps in a local timezone, the 90-day comparison will be wrong. Standardise on UTC everywhere.
- D1 does not support stored procedures or SQL triggers, so the soft-delete stamp must be applied at the application layer on every delete path — HTTP handlers, background jobs, cascade deletes triggered in code.
- `meta.changes` in the purge result is 0 if no rows matched. This is normal on the first run after deployment when no rows are old enough.

## Verification

```sql
-- Confirm a row is soft-deleted
SELECT id, deleted_at FROM items WHERE id = 'abc123';

-- Count live vs deleted
SELECT
  COUNT(*) FILTER (WHERE deleted_at IS NULL)     AS live,
  COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted
FROM items;

-- Preview what the purge cron would remove
SELECT COUNT(*) FROM items
WHERE deleted_at IS NOT NULL
  AND deleted_at < datetime('now', '-90 days');
```

## Related

- `d1-audit-log-application-trigger-workers.md` — log who deleted what
- `d1-cursor-pagination-workers.md` — paginate live items efficiently
- Cloudflare Workers Cron Triggers documentation

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/partialindex.html
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
