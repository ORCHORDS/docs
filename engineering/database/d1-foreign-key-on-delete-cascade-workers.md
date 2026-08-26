# D1 Foreign Key ON DELETE CASCADE Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You delete a parent row (e.g. a `users` record) and expect all child rows across
related tables — orders, sessions, addresses, audit events — to be removed
automatically.  Without cascade rules you must manually delete every child table in
the right order before touching the parent, or you get a foreign-key constraint
violation error at runtime.  You want the database to enforce referential integrity
and automate child cleanup in a single parent DELETE.

---

## Context

SQLite supports `ON DELETE CASCADE`, `ON DELETE SET NULL`, `ON DELETE SET DEFAULT`,
`ON DELETE RESTRICT`, and `ON DELETE NO ACTION` as part of foreign key constraint
syntax.  Cloudflare D1 runs a modern SQLite build that supports all of these.

**Critical caveat**: foreign key enforcement is **off by default** in SQLite.  You
must issue `PRAGMA foreign_keys = ON` before any statement in a connection that should
enforce them.  D1 enables `foreign_keys = ON` by default for Worker bindings (as of
mid-2024), but you should confirm this for your account and not rely on it silently.

`ON DELETE CASCADE` instructs SQLite to automatically delete every child row whose
foreign key column points to the deleted parent row.  Cascades are recursive: a
cascade delete in a child table can trigger further cascades in grandchild tables.

---

## Schema: multi-level cascade

```sql
-- migrations/0040_cascade.sql

CREATE TABLE IF NOT EXISTS users (
  id         TEXT    PRIMARY KEY,
  email      TEXT    NOT NULL UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
) STRICT;

CREATE TABLE IF NOT EXISTS orders (
  id         TEXT    PRIMARY KEY,
  user_id    TEXT    NOT NULL
               REFERENCES users(id) ON DELETE CASCADE,
  total_cents INTEGER NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
) STRICT;

CREATE INDEX idx_orders_user ON orders (user_id);

CREATE TABLE IF NOT EXISTS order_items (
  id         INTEGER PRIMARY KEY,
  order_id   TEXT    NOT NULL
               REFERENCES orders(id) ON DELETE CASCADE,
  sku        TEXT    NOT NULL,
  qty        INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_order_items_order ON order_items (order_id);

-- Sessions cascade-deleted when user is removed.
CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT    PRIMARY KEY,
  user_id    TEXT    NOT NULL
               REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_sessions_user ON sessions (user_id);

-- Audit log: SET NULL instead of cascade — keep the audit record,
-- just disassociate it from the deleted user.
CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY,
  user_id    TEXT             -- NULLable
               REFERENCES users(id) ON DELETE SET NULL,
  action     TEXT    NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
) STRICT;
```

---

## Verifying foreign_keys pragma before writes

```typescript
// src/lib/db-init.ts
import type { D1Database } from '@cloudflare/workers-types';

/**
 * Confirm that D1 has foreign key enforcement enabled.
 * Call once in your Worker's fetch() initialisation path if you need
 * an explicit guarantee rather than relying on the D1 default.
 */
export async function assertForeignKeysEnabled(db: D1Database): Promise<void> {
  const row = await db
    .prepare(`PRAGMA foreign_keys`)
    .first<{ foreign_keys: number }>();

  if (row?.foreign_keys !== 1) {
    // D1 should enable this automatically; this is a safety net.
    await db.prepare(`PRAGMA foreign_keys = ON`).run();
  }
}
```

---

## Deleting a user and all descendants

```typescript
// src/lib/user-service.ts
import type { D1Database } from '@cloudflare/workers-types';

/**
 * Delete a user.  SQLite cascades the delete to:
 *   users -> orders -> order_items   (two-level cascade)
 *   users -> sessions                (one-level cascade)
 *   audit_log.user_id SET NULL       (no row removal — nullification)
 *
 * No manual child-table deletions required.
 */
export async function deleteUser(db: D1Database, userId: string): Promise<boolean> {
  const result = await db
    .prepare(`DELETE FROM users WHERE id = ?1 RETURNING id`)
    .bind(userId)
    .first<{ id: string }>();

  return result !== null;  // false = user did not exist
}
```

---

## Batch delete with cascade verification

```typescript
// src/lib/user-service.ts (continued)

interface DeleteSummary {
  users_deleted: number;
  orders_deleted: number;
  sessions_deleted: number;
}

/**
 * Bulk-purge a list of user accounts and report cascade totals.
 * Each DELETE triggers cascade; we query counts before the delete
 * to report what was removed.
 */
export async function purgeUsers(
  db: D1Database,
  userIds: string[],
): Promise<DeleteSummary> {
  if (userIds.length === 0) return { users_deleted: 0, orders_deleted: 0, sessions_deleted: 0 };

  // Build parameterised IN list.
  const placeholders = userIds.map((_, i) => `?${i + 1}`).join(', ');

  // Count cascade targets before deletion (for reporting).
  const [orderCount, sessionCount] = await Promise.all([
    db
      .prepare(`SELECT COUNT(*) AS n FROM orders WHERE user_id IN (${placeholders})`)
      .bind(...userIds)
      .first<{ n: number }>(),
    db
      .prepare(`SELECT COUNT(*) AS n FROM sessions WHERE user_id IN (${placeholders})`)
      .bind(...userIds)
      .first<{ n: number }>(),
  ]);

  // Single parent DELETE; cascade handles the rest.
  const del = await db
    .prepare(`DELETE FROM users WHERE id IN (${placeholders}) RETURNING id`)
    .bind(...userIds)
    .all<{ id: string }>();

  return {
    users_deleted: del.results.length,
    orders_deleted: orderCount?.n ?? 0,
    sessions_deleted: sessionCount?.n ?? 0,
  };
}
```

---

## SET NULL vs CASCADE: choosing the right action

| Action | Use when |
|---|---|
| `ON DELETE CASCADE` | Child rows are meaningless without the parent (order items, sessions, addresses) |
| `ON DELETE SET NULL` | Child rows have independent value; the FK reference can be nullified (audit log, comments with deleted authors) |
| `ON DELETE RESTRICT` | You want the database to block parent deletion unless all children are removed first (use as a safety net on critical tables) |
| `ON DELETE SET DEFAULT` | Child rows should revert to a default owner/category on parent delete (rare) |
| `ON DELETE NO ACTION` | Deferred constraint check — effectively same as RESTRICT unless using deferred FKs |

---

## Worker handler: GDPR delete-on-request

```typescript
// src/handlers/gdpr-handler.ts
import { deleteUser } from '../lib/user-service';

export async function handleDataDeletion(
  request: Request,
  env: Env,
): Promise<Response> {
  if (request.method !== 'DELETE') return new Response('Method not allowed', { status: 405 });

  const { userId } = await request.json<{ userId: string }>();
  if (!userId) return new Response('userId required', { status: 400 });

  const deleted = await deleteUser(env.DB, userId);
  if (!deleted) return new Response('User not found', { status: 404 });

  return Response.json({ deleted: true, message: 'User and all associated data removed' });
}
```

---

## Adding CASCADE to an existing table

SQLite does not support `ALTER TABLE … ADD CONSTRAINT`.  To add a cascade rule to an
existing foreign key you must recreate the table:

```sql
-- migrations/0041_add_cascade_to_sessions.sql
-- Step 1: Create the new table with the correct constraint.
CREATE TABLE sessions_new (
  token      TEXT    PRIMARY KEY,
  user_id    TEXT    NOT NULL
               REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL
) STRICT;

-- Step 2: Copy data.
INSERT INTO sessions_new SELECT * FROM sessions;

-- Step 3: Drop old, rename new.
DROP TABLE sessions;
ALTER TABLE sessions_new RENAME TO sessions;

-- Step 4: Recreate any indexes.
CREATE INDEX idx_sessions_user ON sessions (user_id);
```

Wrap all four steps in a single migration file so Wrangler applies them atomically.

---

## Anti-patterns

- **Assuming foreign_keys = ON without checking** — on older D1 builds or when
  connecting via the REST API with raw SQL, foreign keys may be off.  An unguarded
  parent delete silently orphans child rows instead of cascading.

- **Cascading into audit/compliance tables** — audit records usually must survive the
  entity they describe.  Use `ON DELETE SET NULL` (or no FK at all) for compliance
  tables where the audit row must be retained.

- **Deep cascade chains without testing** — a 4-level cascade (A → B → C → D) issues
  one DELETE per descendant level.  On large tables this can be slow and may timeout
  under D1's per-request execution limit.  Batch large deletes or schedule them via
  a Queue.

- **Dropping and recreating FK tables without copying data** — a common migration
  mistake.  Always `INSERT INTO new SELECT * FROM old` before dropping the original.

---

## Gotchas

- D1 does not support `DEFERRABLE INITIALLY DEFERRED` foreign keys.  Constraints are
  checked immediately after each statement.  If you need deferred checks (e.g. to
  insert parent and child in reverse order in one transaction), use
  `PRAGMA defer_foreign_keys = ON` for the session.

- Recursive cascades (child table B cascades to grandchild C) are supported but depth
  is limited by SQLite's recursion limit (`PRAGMA recursive_triggers`).  The default
  depth limit is 1 000; normal schemas never approach this.

- `ON DELETE CASCADE` does not fire application-level triggers unless you have defined
  SQLite triggers.  If you need side-effects (e.g. publish an event to a Queue when a
  child row is deleted), do that in application code after the parent delete, not by
  relying on cascade.

- The `RETURNING` clause on a parent DELETE returns only the deleted parent rows, not
  the cascaded child rows.  To know what was deleted downstream, query child tables
  before the parent delete.

---

## Verification

```typescript
import { describe, it, expect, beforeAll } from 'vitest';
import { env } from 'cloudflare:test';
import { deleteUser } from '../src/lib/user-service';

describe('ON DELETE CASCADE', () => {
  beforeAll(async () => { /* apply migrations */ });

  it('cascades user delete to orders and sessions', async () => {
    await env.DB.exec(`
      INSERT INTO users   VALUES ('u1', 'a@b.com', 0);
      INSERT INTO orders  VALUES ('o1', 'u1', 500, 0);
      INSERT INTO order_items VALUES (1, 'o1', 'sku-a', 2);
      INSERT INTO sessions VALUES ('tok1', 'u1', 9999999999);
    `);

    const deleted = await deleteUser(env.DB, 'u1');
    expect(deleted).toBe(true);

    const [orders, items, sessions] = await Promise.all([
      env.DB.prepare('SELECT COUNT(*) AS n FROM orders WHERE user_id = ?').bind('u1').first<{ n: number }>(),
      env.DB.prepare('SELECT COUNT(*) AS n FROM order_items WHERE order_id = ?').bind('o1').first<{ n: number }>(),
      env.DB.prepare('SELECT COUNT(*) AS n FROM sessions WHERE user_id = ?').bind('u1').first<{ n: number }>(),
    ]);

    expect(orders?.n).toBe(0);
    expect(items?.n).toBe(0);
    expect(sessions?.n).toBe(0);
  });

  it('nullifies audit_log.user_id on delete', async () => {
    await env.DB.exec(`
      INSERT INTO users     VALUES ('u2', 'c@d.com', 0);
      INSERT INTO audit_log (user_id, action, created_at) VALUES ('u2', 'login', 0);
    `);

    await deleteUser(env.DB, 'u2');

    const log = await env.DB.prepare('SELECT user_id FROM audit_log WHERE action = ?')
      .bind('login')
      .first<{ user_id: string | null }>();

    expect(log?.user_id).toBeNull();
  });
});
```

---

## Related

- `d1-foreign-keys-referential-integrity.md` — enabling FK enforcement and basic
  constraint patterns in D1.
- `d1-deferred-foreign-key-transaction-workers.md` — using `PRAGMA defer_foreign_keys`
  for deferred constraint evaluation.
- `d1-soft-delete-workers-middleware.md` — soft-delete pattern that avoids triggering
  cascade deletes.
- `d1-temporal-versioning-history-table-workers.md` — keeping history rows when
  cascades would otherwise remove them.

---

## Sources

- SQLite foreign key support: https://www.sqlite.org/foreignkeys.html
- Cloudflare D1 foreign keys: https://developers.cloudflare.com/d1/reference/database-commands/#foreign-key-constraints
- SQLite ALTER TABLE limitations: https://www.sqlite.org/lang_altertable.html
- SQLite RETURNING clause: https://www.sqlite.org/lang_returning.html
