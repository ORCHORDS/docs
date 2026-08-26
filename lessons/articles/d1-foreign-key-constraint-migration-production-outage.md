# D1 Foreign Key Constraint Migration Production Outage

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

All example project post creation, reply, and reaction endpoints began returning HTTP 500 errors. Workers logs showed `SQLITE_CONSTRAINT_FOREIGNKEY` exceptions being thrown from every D1 write that touched the `posts` or `reactions` tables. Reads remained unaffected. The outage started exactly at the moment a schema migration was applied to production.

## Context

example project runs a D1 SQLite database as its primary store. Foreign key enforcement in SQLite is OFF by default and must be explicitly enabled per connection with `PRAGMA foreign_keys = ON`. A migration that added a new `community_id` foreign key column to the `posts` table was applied using Wrangler's `d1 migrations apply` command. The migration file omitted the `PRAGMA foreign_keys = ON` guard and assumed D1 would inherit the session-level pragma from application Workers — which it does not, since D1 connections are stateless across requests.

## Timeline

- **14:00 UTC** — Engineer applies `0042_add_community_id.sql` to production via `wrangler d1 migrations apply example project-prod`.
- **14:01 UTC** — Migration reports success; `wrangler d1 execute` used to verify table schema — looks correct.
- **14:02 UTC** — First HTTP 500 alerts fire across post-creation endpoints.
- **14:04 UTC** — Error logs show: `D1_ERROR: SQLITE_CONSTRAINT_FOREIGNKEY: FOREIGN KEY constraint failed`.
- **14:08 UTC** — On-call engineer checks recent deploys; no Worker code change in last hour. Checks migration log.
- **14:15 UTC** — Hypothesis: foreign key constraints newly active. Engineer queries `PRAGMA foreign_key_list('posts')` in D1 — confirms new FK column.
- **14:20 UTC** — Discovers existing posts rows have `community_id = NULL` but migration added `NOT NULL` with no default and no backfill.
- **14:28 UTC** — Remediation migration written: add default value and backfill existing rows.
- **14:35 UTC** — Remediation applied; HTTP 500s stop.
- **14:37 UTC** — Incident closed; post-mortem scheduled.

## Root Cause

The migration introduced a `NOT NULL` foreign key column without providing a `DEFAULT` value or backfilling existing rows, and without wrapping the operation in a transaction that could be safely rolled back:

```sql
-- migrations/0042_add_community_id.sql — BUGGY VERSION
-- Missing: DEFAULT, backfill, and NOT NULL deferral strategy

ALTER TABLE posts ADD COLUMN community_id TEXT NOT NULL
  REFERENCES communities(id) ON DELETE CASCADE;

-- This creates an immediate constraint on ALL existing rows.
-- Existing rows have community_id = NULL (SQLite sets new columns to NULL
-- unless a DEFAULT is specified), which violates NOT NULL immediately.
-- Every subsequent INSERT also fails because the application did not yet
-- populate community_id in the INSERT statement.
```

The D1 migration applied without error at the DDL level because SQLite's `ALTER TABLE ADD COLUMN` does not validate existing row data against `NOT NULL` unless `STRICT` mode is enabled. However, every subsequent DML write triggered the constraint check, causing all writes to fail.

Additionally, the application Worker code was not yet updated to pass `community_id` in INSERT statements — the Worker deploy was scheduled 10 minutes after the migration, creating a deployment window where the schema was ahead of the application.

## Impact

- **Duration:** 35 minutes (14:02 – 14:37 UTC)
- **Users affected:** All users attempting to post, reply, or react (~6,100 active sessions)
- **Writes blocked:** ~22,400 failed D1 write operations
- **Reads unaffected:** Timeline/feed queries continued normally
- **Data loss:** None (writes failed cleanly; no partial commits)

## Fix

```sql
-- migrations/0043_fix_community_id_backfill.sql — REMEDIATION

-- Step 1: Add column as nullable first
ALTER TABLE posts ADD COLUMN community_id TEXT
  REFERENCES communities(id) ON DELETE SET NULL;

-- Step 2: Backfill existing rows with a sentinel default community
UPDATE posts SET community_id = 'default-community'
WHERE community_id IS NULL;

-- Step 3: D1 does not support ALTER COLUMN to add NOT NULL after the fact
-- (SQLite limitation). If NOT NULL is required, recreate the table.
-- For now, enforce at the application layer and add a CHECK constraint:
-- (D1 CHECK constraints are enforced at insert/update time)
```

```typescript
// workers/posts.ts — application-layer guard added
async function createPost(db: D1Database, payload: CreatePostPayload) {
  if (!payload.communityId) {
    throw new AppError(400, "community_id is required");
  }
  return db.prepare(
    `INSERT INTO posts (id, author_id, content, community_id, created_at)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(),
    payload.authorId,
    payload.content,
    payload.communityId,
    Date.now(),
  ).run();
}
```

The correct long-term migration strategy for adding a non-nullable FK column to a large table:

```sql
-- migrations/0042_add_community_id_safe.sql — CORRECT VERSION

-- Phase 1 (deploy first, before app code): nullable column, no constraint yet
ALTER TABLE posts ADD COLUMN community_id TEXT;

-- Phase 2 (deploy app code that writes community_id): after app is live
-- Phase 3 (backfill): run once app has populated community_id for new rows
UPDATE posts SET community_id = 'default-community' WHERE community_id IS NULL;

-- Phase 4 (enforce): add CHECK or recreate table with NOT NULL
-- This is a separate migration, deployed after confirming zero NULL rows
```

## Prevention

1. **Migration review checklist** added to the deploy runbook:
   - Does the migration add a `NOT NULL` column? → Must include `DEFAULT` or explicit backfill.
   - Does the migration add a FK? → Verify all existing rows satisfy the constraint before applying.
   - Is the migration backward-compatible with the current deployed Worker code?

2. **Pre-migration row count check** added to CI:
```bash
# In deploy script — run before applying migration
wrangler d1 execute example project-prod --command \
  "SELECT COUNT(*) as nulls FROM posts WHERE community_id IS NULL" \
  --json | jq '.result[0].results[0].nulls'
```

3. **Expand/contract migration pattern** documented and enforced: schema changes that break backward compatibility must be split across two deploy cycles.

4. **Staging parity**: production row counts approximated in staging using seeded data; migrations are now validated on a staging clone before production.

5. **Wrangler migration dry-run** (`--dry-run` flag) added to CI pipeline as a mandatory step.

## Anti-patterns

- Applying schema changes at the same time as application code changes (coupled deploy).
- Adding `NOT NULL` columns without a `DEFAULT` or pre-migration backfill.
- Assuming SQLite enforces `NOT NULL` on `ALTER TABLE ADD COLUMN` at DDL time (it does not unless `STRICT`).
- Treating D1 migration success at the DDL level as confirmation that existing data satisfies new constraints.
- Not running migrations against a staging environment with production-representative data volumes.
- Not having a rollback migration ready before applying the forward migration.

## Gotchas

- SQLite (and therefore D1) silently accepts `ALTER TABLE ADD COLUMN ... NOT NULL` without a `DEFAULT` on an empty table but will set existing rows to `NULL`, violating the constraint on next write.
- D1 does not support `ALTER COLUMN` — changing a column's nullability or type requires recreating the table.
- `PRAGMA foreign_keys` must be set per D1 session; it is not persisted. The application Worker must issue `PRAGMA foreign_keys = ON` in the same `D1Database` session before running FK-enforced queries if strict FK checking is desired.
- `wrangler d1 migrations apply` does not rollback on partial failure — migration files should be idempotent.
- D1's SQLite version may differ from local SQLite — always test migrations against `wrangler d1 execute` in remote mode.

## Verification

```sql
-- Verify no NULL community_id rows remain
SELECT COUNT(*) as null_count FROM posts WHERE community_id IS NULL;
-- Expected: 0

-- Verify FK references are valid
SELECT p.id, p.community_id
FROM posts p
LEFT JOIN communities c ON p.community_id = c.id
WHERE c.id IS NULL;
-- Expected: 0 rows
```

```bash
# Confirm migration applied cleanly
wrangler d1 migrations list example project-prod
# Look for 0043 marked as "Applied"
```

Run load test against post-creation endpoint after migration; confirm error rate < 0.1%.

## Related

- `d1-migration-rollback-failed-production-lesson.md`
- `d1-batch-size-limit-exceeded-postmortem.md`
- `d1-write-contention-viral-event-postmortem.md`
- `migrations-must-be-backward-compatible.md`
- `never-delete-without-soft-delete-first.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://www.sqlite.org/foreignkeys.html
- https://www.sqlite.org/stricttables.html
- https://developers.cloudflare.com/d1/reference/d1-api/
