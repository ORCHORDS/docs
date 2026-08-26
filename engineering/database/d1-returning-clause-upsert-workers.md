# D1 RETURNING Clause for Upsert and DML Results in Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

After an `INSERT`, `UPDATE`, or `DELETE` in D1 you need the actual row values — the generated primary key, a server-set `created_at` timestamp, or the full updated record — without issuing a second `SELECT`. You want to retrieve this data atomically and cheaply, especially in upsert flows where the outcome (insert vs update) determines the response body returned to the client.

---

## Context

SQLite has supported the `RETURNING` clause since version 3.35.0 (2021-03-12). D1 runs a recent SQLite build and exposes `RETURNING` through the standard D1 prepared-statement API. `RETURNING` appends a virtual result set to `INSERT`, `UPDATE`, or `DELETE` statements, containing the specified columns from the affected rows at the moment the DML ran. This eliminates a round-trip `SELECT` and prevents TOCTOU races in concurrent environments.

Syntax:
```sql
INSERT INTO t (col) VALUES (?) RETURNING id, created_at;
UPDATE t SET col = ? WHERE id = ? RETURNING *;
DELETE FROM t WHERE id = ? RETURNING id;
```

D1 exposes the returned rows via `.all()` or `.first()` on the prepared statement, the same as a regular `SELECT`.

---

## Basic INSERT … RETURNING

```typescript
// src/handlers/users.ts
import type { D1Database } from '@cloudflare/workers-types';

interface User {
  id: number;
  email: string;
  created_at: number;
}

export async function createUser(
  db: D1Database,
  email: string
): Promise<User> {
  const user = await db
    .prepare(
      `INSERT INTO users (email, created_at)
       VALUES (?, unixepoch())
       RETURNING id, email, created_at`
    )
    .bind(email)
    .first<User>();

  if (!user) throw new Error('Insert did not return a row');
  return user;
}
```

---

## Upsert with RETURNING: Detecting Insert vs Update

`ON CONFLICT … DO UPDATE` combined with `RETURNING` lets you determine whether a row was inserted or updated in a single statement by including a discriminator column:

```sql
CREATE TABLE sessions (
  token      TEXT    PRIMARY KEY,
  user_id    TEXT    NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
  hit_count  INTEGER NOT NULL DEFAULT 1
);
```

```typescript
// src/handlers/sessions.ts
interface SessionResult {
  token: string;
  user_id: string;
  created_at: number;
  updated_at: number;
  hit_count: number;
}

export async function upsertSession(
  db: D1Database,
  token: string,
  userId: string
): Promise<{ session: SessionResult; isNew: boolean }> {
  const session = await db
    .prepare(
      `INSERT INTO sessions (token, user_id)
       VALUES (?, ?)
       ON CONFLICT (token) DO UPDATE SET
         updated_at = unixepoch(),
         hit_count  = hit_count + 1
       RETURNING *, (xmin = ctid) AS is_new`
    )
    .bind(token, userId)
    .first<SessionResult>();

  // SQLite doesn't expose xmin/ctid — use hit_count to detect first insert
  if (!session) throw new Error('Upsert returned no row');
  return { session, isNew: session.hit_count === 1 };
}
```

A cleaner discriminator uses `created_at = updated_at` as a proxy for a freshly inserted row:

```typescript
export async function upsertSessionClean(
  db: D1Database,
  token: string,
  userId: string
): Promise<{ session: SessionResult; isNew: boolean }> {
  const session = await db
    .prepare(
      `INSERT INTO sessions (token, user_id)
       VALUES (?, ?)
       ON CONFLICT (token) DO UPDATE SET
         updated_at = unixepoch(),
         hit_count  = hit_count + 1
       RETURNING *`
    )
    .bind(token, userId)
    .first<SessionResult>();

  if (!session) throw new Error('Upsert returned no row');
  // created_at === updated_at only on the initial insert
  return { session, isNew: session.created_at === session.updated_at };
}
```

---

## UPDATE … RETURNING for Optimistic Locking

```sql
CREATE TABLE documents (
  id      INTEGER PRIMARY KEY,
  content TEXT    NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);
```

```typescript
// src/handlers/documents.ts
interface Document {
  id: number;
  content: string;
  version: number;
}

export async function updateDocumentOptimistic(
  db: D1Database,
  id: number,
  newContent: string,
  expectedVersion: number
): Promise<Document | null> {
  // Returns the updated row only if version matched
  const doc = await db
    .prepare(
      `UPDATE documents
       SET content = ?, version = version + 1
       WHERE id = ? AND version = ?
       RETURNING *`
    )
    .bind(newContent, id, expectedVersion)
    .first<Document>();

  return doc ?? null; // null = version conflict
}
```

---

## DELETE … RETURNING for Soft-delete Archival

```typescript
// src/handlers/archive.ts
interface ArchivedOrder {
  id: number;
  customer_id: string;
  total: number;
  deleted_at: number;
}

export async function deleteAndArchiveOrder(
  db: D1Database,
  orderId: number
): Promise<ArchivedOrder | null> {
  const [deleteResult] = await db.batch([
    db
      .prepare(
        `DELETE FROM orders WHERE id = ?
         RETURNING id, customer_id, total, unixepoch() AS deleted_at`
      )
      .bind(orderId),
  ]);

  const deleted = deleteResult.results[0] as ArchivedOrder | undefined;
  if (!deleted) return null;

  // Archive in the same batch — note: batch executes sequentially
  await db
    .prepare(
      `INSERT INTO archived_orders (id, customer_id, total, deleted_at)
       VALUES (?, ?, ?, ?)`
    )
    .bind(deleted.id, deleted.customer_id, deleted.total, deleted.deleted_at)
    .run();

  return deleted;
}
```

---

## Batch INSERT … RETURNING for Bulk ID Collection

D1's `db.batch()` returns results per statement, making it possible to collect all generated IDs from a batch insert:

```typescript
// src/handlers/bulk-create.ts
interface Tag {
  id: number;
  name: string;
}

export async function bulkCreateTags(
  db: D1Database,
  names: string[]
): Promise<Tag[]> {
  const stmts = names.map((name) =>
    db
      .prepare('INSERT INTO tags (name) VALUES (?) RETURNING id, name')
      .bind(name)
  );

  const results = await db.batch<Tag>(stmts);
  // Each result.results array contains the RETURNING row for that statement
  return results.flatMap((r) => r.results);
}
```

---

## Anti-patterns

- **Using `.run()` with RETURNING** — `.run()` discards result rows; use `.first()` for single-row DML or `.all()` for multi-row deletes. Calling `.run()` on a `RETURNING` statement silently drops the data.
- **Assuming RETURNING fires on no-op upserts** — `ON CONFLICT DO NOTHING` suppresses the insert and produces zero RETURNING rows. Use `DO UPDATE SET col = col` (a self-assignment) to force the upsert to touch the row and emit it via `RETURNING`.
- **Relying on RETURNING to signal row count** — Check `result.results.length` (for `.all()`) or `result !== null` (for `.first()`) to determine whether the DML matched any rows. `meta.changes` is the authoritative row count, but `RETURNING` makes result inspection equally useful.
- **Mixing RETURNING with triggers that modify the same columns** — If an `AFTER UPDATE` trigger on the table modifies the same columns that `RETURNING` references, the `RETURNING` clause reflects the pre-trigger values (the values at DML time). Query the row again if you need post-trigger state.
- **Multi-row UPDATE … RETURNING with `.first()`** — `.first()` returns only the first matched row. Use `.all()` when the UPDATE or DELETE targets multiple rows.

---

## Gotchas

- `RETURNING *` expands to all columns of the target table at parse time. If you add a column via `ALTER TABLE` after deploying a prepared statement, the expansion changes — re-prepare statements that use `RETURNING *` after schema changes.
- D1 does not support server-side prepared statement caching across invocations. Each Worker request re-prepares statements, so there is no stale-plan risk from schema changes.
- `RETURNING` on a table with `DEFAULT (expression)` reflects the evaluated default value, not the expression text. `unixepoch()` in a `DEFAULT` returns the timestamp at row-insert time, which is what you want.
- `RETURNING` is not available inside CTEs used as the body of a DML statement in older SQLite builds. D1's current SQLite version supports it, but test against the D1 SQLite version in CI.
- `last_insert_rowid()` remains valid after a `RETURNING` statement on the same connection; however, in D1's stateless Workers model each request uses a fresh connection context, so do not rely on `last_insert_rowid()` across statements or requests.

---

## Verification

```typescript
// Confirm RETURNING returns the server-generated value
export async function verifyReturning(db: D1Database): Promise<void> {
  const row = await db
    .prepare(
      `INSERT INTO users (email, created_at)
       VALUES ('test@example.com', unixepoch())
       RETURNING id, created_at`
    )
    .first<{ id: number; created_at: number }>();

  console.assert(typeof row?.id === 'number', 'id should be returned');
  console.assert(
    typeof row?.created_at === 'number' && row.created_at > 0,
    'created_at should be a unix timestamp'
  );

  // Cleanup
  await db.prepare('DELETE FROM users WHERE id = ?').bind(row?.id).run();
}
```

---

## Related

- `d1-upsert-conflict-resolution-workers.md`
- `optimistic-locking-version-column.md`
- `d1-soft-delete-workers-middleware.md`
- `d1-batch-operations-performance.md`
- `d1-foreign-keys-referential-integrity.md`

---

## Sources

- https://www.sqlite.org/lang_returning.html
- https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- https://www.sqlite.org/lang_upsert.html
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
