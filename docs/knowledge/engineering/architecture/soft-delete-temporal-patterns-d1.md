# Soft Delete and Temporal Data Patterns with D1 and Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Many production systems require the ability to "delete" a record from the user's perspective while preserving it in the database for audit trails, recovery, compliance (GDPR right to erasure handled separately), undo functionality, or analytics. A hard `DELETE` satisfies none of these requirements. Soft deletes—marking a row as deleted rather than removing it—are the standard solution, but they introduce subtle correctness bugs when not implemented carefully: deleted records leak into queries, unique constraints fail on re-creation, and indexes degrade from carrying dead rows.

Beyond soft deletes, some domains require a full temporal history: "what was the state of this record at time T?" This is the bi-temporal model. On Cloudflare D1 (SQLite), both patterns are achievable without external dependencies, and Workers provide the application layer to enforce their invariants.

## Context

D1 is SQLite under the hood, which means it supports partial indexes (`WHERE deleted_at IS NULL`), generated columns, and `WITHOUT ROWID` tables—all useful for temporal patterns. D1 does not support `PERIOD FOR SYSTEM_TIME` (SQL:2011 temporal tables) natively, so bi-temporal history is implemented in the application layer via explicit version rows.

The Workers application layer enforces soft-delete semantics by injecting `WHERE deleted_at IS NULL` into every query via a repository abstraction. This keeps the guarantee centralized rather than scattered across individual SQL strings.

## Soft Delete Schema and Partial Indexes

Add `deleted_at` to every soft-deleteable table and create a partial index that the query planner uses for all live-record queries:

```sql
-- D1 migration: add soft delete support to the users table
ALTER TABLE users ADD COLUMN deleted_at TEXT;  -- ISO-8601 or NULL

-- Partial index: covers all queries on live records (WHERE deleted_at IS NULL)
CREATE INDEX idx_users_active_email
  ON users (email)
  WHERE deleted_at IS NULL;

-- Unique constraint on live records only
-- SQLite does not support partial unique indexes natively;
-- enforce via a UNIQUE index on a generated column or a trigger:
CREATE TRIGGER enforce_unique_active_email
BEFORE INSERT ON users
WHEN NEW.deleted_at IS NULL
BEGIN
  SELECT RAISE(ABORT, 'Email already in use by an active user')
  WHERE EXISTS (
    SELECT 1 FROM users
    WHERE email = NEW.email AND deleted_at IS NULL AND id != NEW.id
  );
END;
```

## Repository Pattern with Soft Delete Enforcement

A typed repository wraps all D1 queries and automatically filters deleted rows:

```typescript
// src/repositories/user-repository.ts
import { Env } from '../types';

export interface User {
  id: string;
  email: string;
  name: string;
  createdAt: string;
  deletedAt: string | null;
}

export class UserRepository {
  constructor(private readonly db: D1Database) {}

  async findById(id: string): Promise<User | null> {
    return this.db
      .prepare('SELECT * FROM users WHERE id = ? AND deleted_at IS NULL')
      .bind(id)
      .first<User>();
  }

  async findByEmail(email: string): Promise<User | null> {
    return this.db
      .prepare('SELECT * FROM users WHERE email = ? AND deleted_at IS NULL')
      .bind(email)
      .first<User>();
  }

  async findAll(limit = 50, offset = 0): Promise<User[]> {
    const { results } = await this.db
      .prepare('SELECT * FROM users WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?')
      .bind(limit, offset)
      .all<User>();
    return results;
  }

  async create(user: Omit<User, 'deletedAt'>): Promise<void> {
    await this.db
      .prepare('INSERT INTO users (id, email, name, created_at, deleted_at) VALUES (?, ?, ?, ?, NULL)')
      .bind(user.id, user.email, user.name, user.createdAt)
      .run();
  }

  async softDelete(id: string): Promise<boolean> {
    const result = await this.db
      .prepare('UPDATE users SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL')
      .bind(new Date().toISOString(), id)
      .run();
    return result.meta.changes > 0;
  }

  async restore(id: string): Promise<boolean> {
    // Check email uniqueness before restoring
    const user = await this.db
      .prepare('SELECT email FROM users WHERE id = ?')
      .bind(id)
      .first<{ email: string }>();

    if (!user) return false;

    const conflict = await this.findByEmail(user.email);
    if (conflict) throw new Error(`Cannot restore: email ${user.email} is already in use`);

    const result = await this.db
      .prepare('UPDATE users SET deleted_at = NULL WHERE id = ? AND deleted_at IS NOT NULL')
      .bind(id)
      .run();
    return result.meta.changes > 0;
  }

  // Admin-only: find soft-deleted records for audit or recovery
  async findDeleted(since?: string): Promise<User[]> {
    const query = since
      ? 'SELECT * FROM users WHERE deleted_at IS NOT NULL AND deleted_at >= ? ORDER BY deleted_at DESC'
      : 'SELECT * FROM users WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC';
    const { results } = await this.db.prepare(query).bind(...(since ? [since] : [])).all<User>();
    return results;
  }
}
```

## Temporal History (Append-Only Versions Table)

For bi-temporal requirements—"what did this record look like at time T?"—maintain a parallel `_versions` table:

```sql
-- migrations/004_user_versions.sql
CREATE TABLE IF NOT EXISTS user_versions (
  id            TEXT NOT NULL,           -- same as users.id
  version_seq   INTEGER NOT NULL,        -- monotonically increasing per user
  email         TEXT NOT NULL,
  name          TEXT NOT NULL,
  valid_from    TEXT NOT NULL,           -- ISO-8601: when this version became active
  valid_to      TEXT,                    -- NULL = current version
  changed_by    TEXT NOT NULL,           -- actor who made the change
  change_reason TEXT,
  PRIMARY KEY (id, version_seq)
);

CREATE INDEX idx_user_versions_id_time
  ON user_versions (id, valid_from DESC);
```

```typescript
// src/repositories/user-versioned-repository.ts
export class UserVersionedRepository extends UserRepository {
  async updateWithHistory(
    id: string,
    updates: Partial<Pick<User, 'email' | 'name'>>,
    changedBy: string,
    changeReason?: string
  ): Promise<void> {
    const now = new Date().toISOString();

    const current = await this.db
      .prepare('SELECT * FROM users WHERE id = ? AND deleted_at IS NULL')
      .bind(id)
      .first<User & { version_seq: number }>();

    if (!current) throw new Error(`User ${id} not found`);

    await this.db.batch([
      // Close the current version
      this.db.prepare(
        'UPDATE user_versions SET valid_to = ? WHERE id = ? AND valid_to IS NULL'
      ).bind(now, id),

      // Update the live row
      this.db.prepare(
        `UPDATE users SET
           email = COALESCE(?, email),
           name  = COALESCE(?, name)
         WHERE id = ? AND deleted_at IS NULL`
      ).bind(updates.email ?? null, updates.name ?? null, id),

      // Insert new version row
      this.db.prepare(
        `INSERT INTO user_versions
           (id, version_seq, email, name, valid_from, valid_to, changed_by, change_reason)
         VALUES (?, (SELECT COALESCE(MAX(version_seq), 0) + 1 FROM user_versions WHERE id = ?),
                 COALESCE(?, ?), COALESCE(?, ?), ?, NULL, ?, ?)`
      ).bind(
        id, id,
        updates.email ?? null, current.email,
        updates.name ?? null, current.name,
        now, changedBy, changeReason ?? null
      ),
    ]);
  }

  async getAtTime(id: string, asOf: string): Promise<User | null> {
    return this.db
      .prepare(
        `SELECT id, email, name, valid_from AS created_at, NULL AS deleted_at
         FROM user_versions
         WHERE id = ?
           AND valid_from <= ?
           AND (valid_to IS NULL OR valid_to > ?)
         ORDER BY valid_from DESC
         LIMIT 1`
      )
      .bind(id, asOf, asOf)
      .first<User>();
  }
}
```

## GDPR Purge: Hard Delete After Soft Delete

Soft delete alone does not satisfy GDPR erasure. A scheduled Worker purges rows older than the retention window:

```typescript
// src/scheduled/purge.ts
export async function purgeExpiredDeletedUsers(env: Env): Promise<number> {
  const retentionDays = 90;
  const cutoff = new Date(Date.now() - retentionDays * 86_400_000).toISOString();

  // Hard delete the users row
  const { meta: userMeta } = await env.DB.prepare(
    'DELETE FROM users WHERE deleted_at IS NOT NULL AND deleted_at < ?'
  ).bind(cutoff).run();

  // Hard delete the version history (GDPR requirement: no PII retained)
  const { meta: versionMeta } = await env.DB.prepare(
    `DELETE FROM user_versions
     WHERE id NOT IN (SELECT id FROM users)
       AND valid_from < ?`
  ).bind(cutoff).run();

  console.log(`Purged ${userMeta.changes} users, ${versionMeta.changes} version rows`);
  return userMeta.changes;
}
```

Wire into a `scheduled` Worker handler:

```typescript
// src/index.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await purgeExpiredDeletedUsers(env);
  },
};
```

## Anti-patterns

- Omitting `AND deleted_at IS NULL` from any query that should see only live records—this is the most common bug with soft deletes and is best prevented by centralizing all queries in a repository.
- Allowing re-creation of records with the same natural key (e.g., email) without first restoring the soft-deleted row—leads to duplicate PII and broken references.
- Storing soft-deleted rows in the same indexes as live rows without using partial indexes—the full table scan penalty accumulates as deleted rows grow.
- Using soft delete as the sole GDPR erasure mechanism—soft-deleted rows still contain PII; a purge step is mandatory.
- Never purging soft-deleted rows—tables accumulate unbounded rows, degrading query performance and violating retention policies.

## Gotchas

- SQLite's partial unique indexes require the `WHERE` clause to match the query predicate exactly; D1 will use the partial index only when the query also contains `AND deleted_at IS NULL`.
- D1 does not support `GENERATED ALWAYS AS` columns in the same statement as a UNIQUE constraint—split into separate `ALTER TABLE` and `CREATE INDEX` statements.
- The `version_seq` computed via `MAX(version_seq) + 1` inside a batch is safe only because D1 batch statements execute sequentially and atomically. Do not compute this in application code concurrently.
- `ctx.waitUntil()` can run the purge asynchronously after a response, but scheduled Workers already run outside the request cycle—no `waitUntil()` is needed in the `scheduled` handler.
- When soft-deleting a record that has foreign keys pointing to it, decide whether child records should also be soft-deleted (cascade) or left orphaned. Implement cascade in the repository layer, not as a D1 trigger, to keep logic visible.

## Verification

1. Create a user, soft-delete them, then `SELECT * FROM users WHERE id = ?`—confirm `deleted_at` is set.
2. Query `findById()` for the soft-deleted user via the repository—confirm it returns `null`.
3. Attempt to create a second user with the same email while the first is soft-deleted—confirm the trigger raises an error.
4. Restore the first user and confirm `deleted_at` is `NULL` again.
5. Update the user's name via `updateWithHistory()` and query `getAtTime()` with a timestamp before the update—confirm the old name is returned.
6. Set `deleted_at` to a date 91 days ago and run `purgeExpiredDeletedUsers()`—confirm the row is fully removed from `users` and `user_versions`.

## Related

- `event-sourcing-d1-append-only-store.md` — storing full event history rather than only the latest version
- `change-data-capture-d1-queues.md` — streaming D1 row changes to downstream consumers
- `audit-log` — append-only audit trail patterns
- `idempotency-design.md` — safe retries for delete and restore operations

## Sources

- SQLite partial indexes documentation: https://www.sqlite.org/partialindex.html
- GDPR Article 17 (Right to erasure): https://gdpr.eu/right-to-be-forgotten/
- "SQL and Relational Theory" by C. J. Date — temporal data modeling
