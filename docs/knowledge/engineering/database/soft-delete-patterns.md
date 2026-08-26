# Soft Delete Patterns

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Posts and user accounts reappear in feed queries after a user
deletes them because the `WHERE deleted_at IS NULL` filter was
omitted in one endpoint. Alternatively, content is hard-deleted
by mistake, losing moderation history and breaking foreign-key
references. A GDPR erasure request arrives, but the team is
unsure whether soft-delete alone satisfies Article 17.

## Context

Soft delete marks a row as removed without physically deleting
it. The row stays in the table; every query that should respect
the deletion must filter it out. This pattern is standard in
anonymous social apps because:

- Moderation needs audit history of deleted posts.
- Users may want to undo a deletion within a grace period.
- GDPR right-to-erasure requires eventual hard deletion of PII.
- FK integrity is easier to maintain when rows still exist.

## Schema — The deleted_at Column

```sql
ALTER TABLE posts
  ADD COLUMN deleted_at INTEGER; -- Unix ms, NULL = live

ALTER TABLE users
  ADD COLUMN deleted_at INTEGER;

-- Partial index: only live rows appear in feed queries
CREATE INDEX idx_posts_board_live
  ON posts (board_id, created_at DESC)
  WHERE deleted_at IS NULL;

-- Unique handle only among live users
CREATE UNIQUE INDEX uq_users_handle_live
  ON users (handle)
  WHERE deleted_at IS NULL;

-- Index to support purge-cron range scan
CREATE INDEX idx_posts_deleted_at
  ON posts (deleted_at)
  WHERE deleted_at IS NOT NULL;
```

Using `INTEGER` (Unix milliseconds) rather than `TEXT` is
idiomatic for SQLite/D1 and sorts correctly without casting.

## Excluding Soft-Deleted Rows — Views

Create a view so application queries never forget the filter.
Route all read queries through the view; only purge jobs and
moderation endpoints reference the base table directly.

```sql
CREATE VIEW live_posts AS
  SELECT * FROM posts WHERE deleted_at IS NULL;

CREATE VIEW live_users AS
  SELECT * FROM users WHERE deleted_at IS NULL;
```

D1/SQLite has no materialised views or row-level security.
Enforce the view convention in code review so no endpoint
queries the base table directly.

## Cascading Soft Deletes

When a user is soft-deleted, their posts and comments should
also be marked. D1 has no trigger support via the HTTP API;
cascade in application code using `db.batch()`:

```ts
const now = Date.now();
await db.batch([
  db.prepare('BEGIN'),
  db.prepare(
    'UPDATE posts SET deleted_at=?1 WHERE author_id=?2'
  ).bind(now, userId),
  db.prepare(
    'UPDATE comments SET deleted_at=?1 WHERE author_id=?2'
  ).bind(now, userId),
  db.prepare(
    'UPDATE users SET deleted_at=?1 WHERE id=?2'
  ).bind(now, userId),
  db.prepare('COMMIT'),
]);
```

Update child rows (posts, comments) before the parent (users).
Wrap in `BEGIN` / `COMMIT` for atomicity.

## Undelete Flow and Grace Period

Allow a user to restore a deleted post within 30 minutes:

```ts
const GRACE_MS = 30 * 60 * 1000;

const result = await db
  .prepare(`
    UPDATE posts
    SET    deleted_at = NULL
    WHERE  id         = ?1
      AND  deleted_at IS NOT NULL
      AND  deleted_at > ?2
  `)
  .bind(postId, Date.now() - GRACE_MS)
  .run();

if (result.meta.changes === 0) {
  // Either not found, not deleted, or grace expired
  throw new Error('Post cannot be restored');
}
```

Return an error when the grace period has expired.

## Purge Jobs and GDPR Hard Deletion

Soft delete alone does not satisfy GDPR Article 17. A
Cloudflare Cron Trigger Worker must hard-delete PII after the
retention window. Suggested windows:

| Table    | Grace (undelete) | Hard-delete after    |
|----------|------------------|----------------------|
| posts    | 30 min           | 30 days              |
| comments | 30 min           | 30 days              |
| users    | 7 days           | 30 days (or on GDPR  |
|          |                  | erasure request)     |
| votes    | immediate        | 7 days               |
| sessions | immediate        | 7 days               |

A Cron Trigger Worker runs daily and issues `DELETE FROM
posts WHERE deleted_at < cutoff` using `db.batch()`. For
a GDPR right-to-erasure request, trigger an immediate purge
of PII columns and log the event to a compliance audit table
that is itself exempt from the standard purge policy.

## Anti-patterns

- **Querying the base table directly** — every caller must
  remember `WHERE deleted_at IS NULL`; use the view instead.
- **Using a boolean `is_deleted`** — loses the deletion
  timestamp needed for grace-period undelete and cron purge.
- **Treating soft delete as permanent erasure** — soft delete
  alone does not satisfy GDPR Article 17; schedule hard delete.
- **Cascading in a loop** — N round-trips to D1; use one
  batch with `BEGIN` / `COMMIT`.

## Gotchas

- SQLite/D1 has no `ON DELETE CASCADE` for soft deletes; you
  must implement cascades in application code.
- A view in SQLite is not updatable; writes still go to the
  base table, which is correct for this pattern.
- Unique partial indexes can conflict on restore: if another
  user claimed a handle during the deletion window, the
  restore will throw a unique-constraint violation.
- Log erasure events (user id, timestamp, initiator) to a
  compliance audit table; the audit table is not soft-deleted.

## Verification

```sql
-- Confirm view excludes deleted rows
SELECT COUNT(*) FROM live_posts;
SELECT COUNT(*) FROM posts WHERE deleted_at IS NULL;
-- Both must return the same number.

-- Confirm purge cron uses the index
EXPLAIN QUERY PLAN
  DELETE FROM posts
  WHERE deleted_at IS NOT NULL
    AND deleted_at < 1700000000000;
-- Expected: SEARCH posts USING INDEX idx_posts_deleted_at
```

## Related

- `database/soft-delete-schema-design.md`
- `database/partial-indexes.md`
- `database/audit-columns-pattern.md`
- `database/data-retention-deletion.md`
- `compliance/gdpr-right-to-erasure.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/d1/platform/client-api/
- https://www.sqlite.org/partialindex.html
- https://gdpr-info.eu/art-17-gdpr/
- https://developers.cloudflare.com/workers/runtime-apis/
  handlers/scheduled/
