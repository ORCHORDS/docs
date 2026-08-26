# d1-foreign-keys

**Issue:** Enabling and using foreign keys in Cloudflare D1 (SQLite)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SQLite (and therefore D1) has foreign key enforcement **disabled by default**. You must explicitly enable it per connection, or referential integrity is silently not enforced. This catches many developers off guard when migrating from Postgres.

## Pattern / Solution

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Enable FK enforcement for this connection (do this once, early)
    await env.DB.exec('PRAGMA foreign_keys = ON');

    // Now foreign key constraints are enforced
    try {
      await env.DB.prepare(
        `DELETE FROM users WHERE id = ?`
      ).bind(1).run();
    } catch (err) {
      // Throws if a child row references users.id = 1
      return Response.json({ error: 'Cannot delete: referenced by child rows' }, { status: 409 });
    }

    return Response.json({ ok: true });
  },
};
```

**Schema example with foreign keys:**
```sql
-- migrations/0001_create_tables.sql
PRAGMA foreign_keys = ON;

CREATE TABLE users (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  email    TEXT NOT NULL UNIQUE,
  created  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE posts (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title     TEXT NOT NULL,
  body      TEXT NOT NULL
);

CREATE TABLE comments (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id  INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
  body     TEXT NOT NULL
);
```

**ON DELETE / ON UPDATE actions:**
| Action | Behaviour |
|---|---|
| `CASCADE` | Delete/update child rows automatically |
| `SET NULL` | Set FK column to NULL |
| `SET DEFAULT` | Set FK column to its DEFAULT value |
| `RESTRICT` | Prevent delete/update if children exist |
| `NO ACTION` | Same as RESTRICT but deferred |

## Gotchas
- `PRAGMA foreign_keys = ON` must be run **in every connection / isolate startup** — it does not persist across connections.
- D1's `exec()` runs DDL; use `prepare().run()` for DML within the same session.
- `ON DELETE CASCADE` can cause large cascading deletes — profile with `EXPLAIN QUERY PLAN` on large tables.
- `PRAGMA foreign_keys` cannot be changed inside a transaction.
- Foreign key columns should be indexed for performance: `CREATE INDEX idx_posts_user_id ON posts(user_id)`.
- D1 does not support deferred FK constraints (`DEFERRABLE INITIALLY DEFERRED`) in the same way as Postgres.

## Related
- `d1-best-practices.md`
- `d1-transactions-isolation.md`
- `d1-migration-best-practices.md`
