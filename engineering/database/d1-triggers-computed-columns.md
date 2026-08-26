# D1 Triggers and Computed Columns for Denormalized Data
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You need denormalized aggregates or derived columns in Cloudflare D1 (SQLite) without running
application-level bookkeeping on every write. Examples: a `comment_count` on a `posts` table
that must stay consistent, a `full_name` column kept in sync with `first_name`/`last_name`, or
a `last_activity_at` timestamp that must reflect the latest child row across several tables.

## Context

D1 runs a managed SQLite engine exposed over Cloudflare's HTTP API. SQLite has supported
`CREATE TRIGGER` and `GENERATED COLUMNS` since 3.25 (2018) and 3.31 (2020) respectively.
Both features survive D1's managed migrations workflow and can be declared inside Wrangler
migration files. Unlike Postgres, SQLite triggers are row-level only (no statement-level
triggers), and generated columns cannot reference other tables. Understanding those constraints
prevents architecture missteps when designing for D1.

D1's query API is synchronous within a single `prepare().bind().run()` call, which means
triggers fire atomically within the same SQLite transaction — no race windows at the
application layer.

---

## Generated Columns (Computed Columns)

SQLite distinguishes two variants:

| Variant | Storage | Recomputed on |
|---------|---------|---------------|
| `VIRTUAL` | Not stored | Every SELECT |
| `STORED` | Persisted to disk | Every INSERT/UPDATE |

`STORED` is preferable for D1 because it avoids per-row computation during reads and plays
well with indexes.

```sql
-- migrations/0005_add_full_name_generated.sql
ALTER TABLE users
  ADD COLUMN full_name TEXT
    GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED;

-- Index the generated column for search
CREATE INDEX idx_users_full_name ON users (full_name);
```

Query with no app-layer concatenation:

```sql
SELECT id, full_name, email
FROM   users
WHERE  full_name LIKE 'Jane%';
```

### Limitations of Generated Columns

- Cannot reference other tables (no subqueries).
- Cannot call non-deterministic functions (`random()`, `datetime('now')`).
- Cannot be updated directly with `INSERT ... VALUES` or `UPDATE SET`.
- The expression must be deterministic and self-contained within the row.

For cross-table derived values, use triggers instead.

---

## Triggers for Cross-Table Denormalization

### Pattern 1 — Maintaining a `comment_count` on `posts`

```sql
-- migrations/0006_comment_count_triggers.sql

-- Ensure the column exists with a default
ALTER TABLE posts ADD COLUMN comment_count INTEGER NOT NULL DEFAULT 0;

-- Back-fill from existing data (run once at migration time)
UPDATE posts
SET    comment_count = (
  SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id
);

-- Increment on new comment
CREATE TRIGGER trg_comments_after_insert
AFTER INSERT ON comments
BEGIN
  UPDATE posts
  SET    comment_count = comment_count + 1
  WHERE  id = NEW.post_id;
END;

-- Decrement on hard delete
CREATE TRIGGER trg_comments_after_delete
AFTER DELETE ON comments
BEGIN
  UPDATE posts
  SET    comment_count = comment_count - 1
  WHERE  id = OLD.post_id;
END;

-- Handle re-parenting (unlikely but defensive)
CREATE TRIGGER trg_comments_after_update
AFTER UPDATE OF post_id ON comments
WHEN OLD.post_id != NEW.post_id
BEGIN
  UPDATE posts SET comment_count = comment_count - 1 WHERE id = OLD.post_id;
  UPDATE posts SET comment_count = comment_count + 1 WHERE id = NEW.post_id;
END;
```

### Pattern 2 — Rolling `last_activity_at` across child events

```sql
-- migrations/0007_project_last_activity.sql

ALTER TABLE projects ADD COLUMN last_activity_at INTEGER;  -- Unix epoch

CREATE TRIGGER trg_tasks_insert_activity
AFTER INSERT ON tasks
WHEN NEW.project_id IS NOT NULL
BEGIN
  UPDATE projects
  SET    last_activity_at = strftime('%s', 'now')
  WHERE  id = NEW.project_id
    AND  (last_activity_at IS NULL OR last_activity_at < strftime('%s', 'now'));
END;

CREATE TRIGGER trg_tasks_update_activity
AFTER UPDATE ON tasks
WHEN NEW.project_id IS NOT NULL
BEGIN
  UPDATE projects
  SET    last_activity_at = strftime('%s', 'now')
  WHERE  id = NEW.project_id;
END;

CREATE TRIGGER trg_comments_insert_activity
AFTER INSERT ON comments
BEGIN
  UPDATE projects
  SET    last_activity_at = strftime('%s', 'now')
  WHERE  id = (SELECT project_id FROM tasks WHERE id = NEW.task_id LIMIT 1);
END;
```

### Pattern 3 — Soft-delete aware aggregate

When rows are soft-deleted, a simple `+1/-1` counter breaks. Recompute from a correlated
subquery instead:

```sql
CREATE TRIGGER trg_comments_soft_delete
AFTER UPDATE OF deleted_at ON comments
WHEN (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL)
   OR (OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL)
BEGIN
  UPDATE posts
  SET comment_count = (
    SELECT COUNT(*)
    FROM   comments
    WHERE  post_id = NEW.post_id
      AND  deleted_at IS NULL
  )
  WHERE id = NEW.post_id;
END;
```

---

## Applying Triggers via Wrangler Migrations

D1 migrations are plain SQL files executed in order. Triggers are DDL, so they belong in a
numbered migration file.

```bash
# Generate a new migration file
npx wrangler d1 migrations create example project-db "add_comment_count_triggers"
# Creates migrations/0006_add_comment_count_triggers.sql
```

```typescript
// src/migrate.ts — run during Worker startup or a cron trigger
import { Env } from "./types";

export async function runMigrations(env: Env) {
  await env.DB.exec(`PRAGMA journal_mode=WAL`);
  // Wrangler applies migration files automatically via `wrangler d1 migrations apply`
  // For programmatic use, exec the SQL directly:
  const sql = await fetch(new URL("../migrations/0006_add_comment_count_triggers.sql", import.meta.url));
  await env.DB.exec(await sql.text());
}
```

In CI, apply before running integration tests:

```bash
npx wrangler d1 migrations apply example project-db --local
npx vitest run
```

---

## Anti-patterns

- **Trigger chains without depth limits**: SQLite does not cap trigger recursion by default.
  Circular triggers (A updates B, B updates A) will loop until `SQLITE_MAX_TRIGGER_DEPTH` is
  hit (default 1000) and throw. Keep triggers unidirectional.

- **Application-layer fallback beside triggers**: If the app also increments the counter, you
  get double-counting on writes. Choose one layer — triggers *or* application code.

- **Using `VIRTUAL` generated columns in WHERE clauses without an index**: A `VIRTUAL` column
  must be recomputed for every row during a full scan. Either switch to `STORED` and index, or
  index the underlying expression with `CREATE INDEX ... ON t (expr(...))`.

- **Mixing triggers with D1 batch API without awareness**: D1's `batch()` runs each statement
  as its own implicit transaction. Triggers fire per statement. Ensure the trigger's logic is
  idempotent when batching multiple inserts.

---

## Gotchas

- **`strftime('%s', 'now')`** returns a TEXT string in SQLite, not INTEGER. Cast explicitly:
  `CAST(strftime('%s', 'now') AS INTEGER)` when storing in an INTEGER column.

- **`WHEN` clause in triggers**: SQLite evaluates the `WHEN` clause before running the trigger
  body. An error in the `WHEN` expression still rolls back the parent statement.

- **D1 does not surface trigger errors differently**: If a trigger raises a constraint
  violation, the parent `INSERT`/`UPDATE`/`DELETE` fails with `D1_ERROR` and the same error
  text as a regular constraint failure. Log `cause` in your Worker to diagnose.

- **Generated columns and ALTER TABLE**: You cannot `ALTER COLUMN` in SQLite. To change a
  generated column expression, you must recreate the table (create new, copy data, drop old,
  rename). Plan expressions carefully before shipping.

- **Trigger visibility in `wrangler d1 execute --command`**: `SELECT * FROM sqlite_master WHERE type='trigger'`
  lists all triggers in the database. Verify after migrations apply.

---

## Verification

```sql
-- List all triggers
SELECT name, tbl_name, sql
FROM   sqlite_master
WHERE  type = 'trigger'
ORDER  BY tbl_name, name;

-- Verify generated column is indexed
SELECT name, sql
FROM   sqlite_master
WHERE  type = 'index'
  AND  sql LIKE '%full_name%';

-- Sanity-check counter consistency
SELECT p.id,
       p.comment_count                          AS stored_count,
       COUNT(c.id)                              AS real_count,
       p.comment_count - COUNT(c.id)            AS drift
FROM   posts p
LEFT   JOIN comments c ON c.post_id = p.id AND c.deleted_at IS NULL
GROUP  BY p.id
HAVING drift != 0;
```

Run the drift query after any bulk data migration to ensure triggers fired correctly.

---

## Related

- `d1-foreign-keys-referential-integrity.md` — cascade delete interacts with counter triggers
- `d1-batch-operations-performance.md` — batch writes and trigger firing order
- `sqlite-journal-modes.md` — WAL mode affects trigger visibility across connections
- `d1-schema-versioning-wrangler-migrations.md` — migration file conventions
- `generated-columns.md` — Postgres equivalent for comparison

## Sources

- SQLite Triggers: https://www.sqlite.org/lang_createtrigger.html
- SQLite Generated Columns: https://www.sqlite.org/gencol.html
- Cloudflare D1 Migrations: https://developers.cloudflare.com/d1/reference/migrations/
- SQLite `sqlite_master` schema table: https://www.sqlite.org/schematab.html
