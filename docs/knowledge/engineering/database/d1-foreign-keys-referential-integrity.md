# d1-foreign-keys-referential-integrity

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

In a example project D1 schema with `posts.community_id REFERENCES communities(id)`,
deleting a community row leaves orphaned post rows behind. No error is
thrown. Foreign key constraints exist in the migration SQL but are
silently ignored at runtime because SQLite (and therefore D1) disables
foreign key enforcement by default and requires an explicit `PRAGMA`
to activate it.

## Context

SQLite ships with foreign key enforcement OFF by default for backward
compatibility. The `FOREIGN KEY` clause is parsed and stored in the
schema but has no runtime effect unless the session enables it with:

```sql
PRAGMA foreign_keys = ON;
```

This pragma is connection-scoped and resets to OFF on every new
connection. In Cloudflare D1, each Worker invocation receives a fresh
connection, so the PRAGMA must be issued at the start of every Worker
request that needs FK enforcement.

D1's HTTP-based protocol means "connections" are not persistent;
Cloudflare manages the underlying SQLite file access. The PRAGMA still
works but must be included in every request session.

## Enabling Foreign Keys in a D1 Worker

Issue `PRAGMA foreign_keys = ON` before any other statement. The
cleanest approach in example project Workers is a middleware helper:

```typescript
// lib/db.ts
export async function withForeignKeys(db: D1Database): Promise<void> {
  await db.prepare("PRAGMA foreign_keys = ON").run();
}
```

```typescript
// routes/community-delete.ts
export async function handleDeleteCommunity(
  req: Request,
  env: Env
): Promise<Response> {
  await withForeignKeys(env.DB);

  // Now FK constraints are active for this request.
  try {
    await env.DB
      .prepare("DELETE FROM communities WHERE id = ?")
      .bind(communityId)
      .run();
  } catch (err: unknown) {
    if (
      err instanceof Error &&
      err.message.includes("FOREIGN KEY constraint failed")
    ) {
      return Response.json(
        { error: "community_has_posts" },
        { status: 409 }
      );
    }
    throw err;
  }
  return new Response(null, { status: 204 });
}
```

Alternatively, include the PRAGMA as the first item in a `db.batch()`:

```typescript
const [, result] = await env.DB.batch([
  env.DB.prepare("PRAGMA foreign_keys = ON"),
  env.DB.prepare("DELETE FROM communities WHERE id = ?").bind(id),
]);
```

## Cascade Delete Pattern

Define cascade deletes in the migration schema so that deleting a
parent row automatically removes all children:

```sql
-- migrations/0004_add_fk_constraints.sql
PRAGMA foreign_keys = ON;

CREATE TABLE posts (
  id          TEXT PRIMARY KEY,
  community_id TEXT NOT NULL
    REFERENCES communities(id) ON DELETE CASCADE,
  body        TEXT NOT NULL,
  score       INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL
);

CREATE TABLE votes (
  post_id     TEXT NOT NULL
    REFERENCES posts(id) ON DELETE CASCADE,
  fingerprint TEXT NOT NULL,
  direction   INTEGER NOT NULL,
  PRIMARY KEY (post_id, fingerprint)
);

CREATE TABLE comments (
  id      TEXT PRIMARY KEY,
  post_id TEXT NOT NULL
    REFERENCES posts(id) ON DELETE CASCADE,
  body    TEXT NOT NULL
);
```

With `ON DELETE CASCADE`:
- Deleting a community cascades to all its posts.
- Deleting a post cascades to its votes and comments.
- The PRAGMA must still be ON at runtime for cascades to fire.

## Constraint Violation Error Handling

D1 surfaces SQLite error codes in the `Error` message string. Parse
them to return meaningful API errors:

```typescript
function handleD1Error(err: unknown): Response {
  const msg = err instanceof Error ? err.message : String(err);

  if (msg.includes("FOREIGN KEY constraint failed")) {
    return Response.json(
      { error: "referential_integrity_violation" },
      { status: 409 }
    );
  }
  if (msg.includes("UNIQUE constraint failed")) {
    const col = msg.match(/UNIQUE constraint failed: (.+)/)?.[1] ?? "";
    return Response.json(
      { error: "duplicate_value", field: col },
      { status: 409 }
    );
  }
  if (msg.includes("NOT NULL constraint failed")) {
    return Response.json(
      { error: "missing_required_field" },
      { status: 400 }
    );
  }

  // Unknown — re-throw for 500 handling
  throw err;
}
```

## Migration Strategy for Existing Tables

Adding FK constraints to an existing D1 table without recreating it
is not supported in SQLite (ALTER TABLE cannot add constraints). The
migration must recreate the table:

```sql
-- migrations/0010_add_posts_fk.sql

PRAGMA foreign_keys = OFF;   -- avoid FK checks during migration

BEGIN;

CREATE TABLE posts_new (
  id           TEXT PRIMARY KEY,
  community_id TEXT NOT NULL
    REFERENCES communities(id) ON DELETE CASCADE,
  body         TEXT NOT NULL,
  score        INTEGER NOT NULL DEFAULT 0,
  created_at   INTEGER NOT NULL
);

INSERT INTO posts_new SELECT * FROM posts;

DROP TABLE posts;

ALTER TABLE posts_new RENAME TO posts;

COMMIT;

PRAGMA foreign_keys = ON;
```

Run orphan cleanup before this migration to avoid FK violations during
the INSERT INTO posts_new:

```sql
DELETE FROM posts
WHERE community_id NOT IN (SELECT id FROM communities);
```

## PRAGMA in D1 Batch Context

When using `db.batch()`, include the PRAGMA as the first statement.
It affects all subsequent statements in the same batch session:

```typescript
await env.DB.batch([
  env.DB.prepare("PRAGMA foreign_keys = ON"),
  env.DB.prepare(
    "INSERT INTO posts (id, community_id, body, score, created_at)"
    + " VALUES (?, ?, ?, 0, ?)"
  ).bind(postId, communityId, body, now),
]);
// FK enforcement active: INSERT will fail if communityId doesn't exist.
```

## Anti-Patterns

- Defining `REFERENCES` in the schema but never issuing
  `PRAGMA foreign_keys = ON`—constraints are silently ignored.
- Running `PRAGMA foreign_keys = ON` inside a migration file and
  expecting it to persist to Worker runtime—it resets per connection.
- Using `ON DELETE SET NULL` without declaring the column `NULL`able—
  SQLite will reject the constraint at table-creation time.
- Skipping orphan cleanup before a recreate-migration—the INSERT into
  the new table fails if orphaned rows violate the new FK constraint.

## Gotchas

- D1 does not expose a way to check whether foreign keys are currently
  ON for a session; always issue the PRAGMA defensively.
- `PRAGMA foreign_keys` is not honored inside `db.exec()` multi-
  statement strings in some D1 versions—use `db.prepare().run()` or
  `db.batch()` with the PRAGMA as the first element.
- Cascade deletes can be slow on large child tables without indexes on
  the FK column. Always index every FK column:
  `CREATE INDEX idx_posts_community_id ON posts(community_id);`
- SQLite's `ON DELETE RESTRICT` and `ON DELETE NO ACTION` behave
  identically in deferred mode—use `RESTRICT` for immediate checking.

## Verification

```bash
# Confirm FK enforcement is working after PRAGMA via wrangler:
wrangler d1 execute example project-prod --command \
  "PRAGMA foreign_keys = ON; \
   INSERT INTO posts (id, community_id, body, score, created_at) \
   VALUES ('test-1', 'nonexistent-community', 'hi', 0, 0);"

# Expected: Error: FOREIGN KEY constraint failed
# Actual before fix: row inserted silently.

# Check for orphaned rows in production:
wrangler d1 execute example project-prod --command \
  "SELECT COUNT(*) AS orphaned FROM posts \
   WHERE community_id NOT IN (SELECT id FROM communities);"
# Expected: 0
```

## Related

- `database/d1-migrations-wrangler-ci-cd.md`
- `database/d1-batch-operations-performance.md`
- `database/foreign-key-constraints.md`
- `database/check-constraints.md`

## Sources

- https://www.sqlite.org/foreignkeys.html
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://developers.cloudflare.com/d1/sql-api/sql-statements/
