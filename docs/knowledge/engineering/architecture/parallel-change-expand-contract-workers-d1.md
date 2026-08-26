# Parallel Change (Expand–Contract) Schema Migration in Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to rename a D1 column, split one column into two, or change a column's type while
the Worker serving production traffic cannot be taken offline. A standard `ALTER TABLE` or
`DROP COLUMN` with a same-time code deploy risks a window where new code references columns
that do not yet exist, or old code writes to columns the new schema dropped.

The Parallel Change (also called Expand–Contract or Expand–Migrate–Contract) pattern
eliminates that window by making schema and code changes in three independently deployable
phases.

---

## Context

D1 is a SQLite-compatible database. SQLite ALTER TABLE is limited (no column rename in
older SQLite versions, no type changes, no multi-column constraints in a single statement).
D1 is eventually consistent across read replicas; the primary receives writes, and replicas
lag by milliseconds to seconds. This makes schema migrations that require strict ordering
especially important to sequence carefully.

The three phases are:

| Phase | Schema | Code |
|-------|--------|------|
| Expand | Add new column(s); keep old column(s) | Write to BOTH old and new; read from old |
| Migrate | Back-fill old rows | (no code change needed) |
| Contract | Drop old column(s) | Read from new; stop writing to old |

Each phase is a separate Worker deployment with its own D1 migration file. Zero traffic is
lost between phases.

---

## Running Example

Goal: rename `user_email` → `contact_email` in a `users` table.

Initial schema:

```sql
-- migrations/0001_initial.sql
CREATE TABLE users (
  id      TEXT PRIMARY KEY,
  name    TEXT NOT NULL,
  user_email TEXT NOT NULL
);
```

---

## Phase 1 — Expand

Add the new column. Do not drop the old one yet.

```sql
-- migrations/0002_expand_contact_email.sql
ALTER TABLE users ADD COLUMN contact_email TEXT;
```

Deploy the migration first, then deploy the Worker code that writes to both columns and
reads from the old one:

```typescript
// src/users/repository.ts  (Phase 1 code)

export async function createUser(
  db: D1Database,
  id: string,
  name: string,
  email: string
): Promise<void> {
  await db
    .prepare(`
      INSERT INTO users (id, name, user_email, contact_email)
      VALUES (?, ?, ?, ?)
    `)
    .bind(id, name, email, email) // write to BOTH
    .run();
}

export async function getUserEmail(db: D1Database, id: string): Promise<string | null> {
  const row = await db
    .prepare("SELECT user_email FROM users WHERE id = ?") // read from OLD
    .bind(id)
    .first<{ user_email: string }>();
  return row?.user_email ?? null;
}
```

At this point any old code still reading `user_email` continues to work because the column
still exists. New rows get both columns populated.

---

## Phase 2 — Migrate (Back-fill)

Run a back-fill to populate `contact_email` for rows that existed before Phase 1. This is
safe to run while the Worker is live because:

- No existing column is removed.
- The query only touches rows where `contact_email IS NULL`.

```typescript
// scripts/backfill-contact-email.ts  (run via wrangler d1 execute)

// Execute via:
//   wrangler d1 execute DB --file=migrations/0003_backfill_contact_email.sql
```

```sql
-- migrations/0003_backfill_contact_email.sql
UPDATE users
SET contact_email = user_email
WHERE contact_email IS NULL;
```

For very large tables, batch the update to avoid locking:

```sql
-- Run repeatedly until 0 rows affected
UPDATE users
SET contact_email = user_email
WHERE contact_email IS NULL
LIMIT 500;
```

Verify completion:

```sql
SELECT COUNT(*) AS unbackfilled FROM users WHERE contact_email IS NULL;
-- Must return 0 before proceeding to Phase 3
```

---

## Phase 3 — Contract

Switch reads to the new column, stop writing to the old one, then drop it.

Deploy code first (so no new writes go to the old column), then run the migration.

```typescript
// src/users/repository.ts  (Phase 3 code)

export async function createUser(
  db: D1Database,
  id: string,
  name: string,
  email: string
): Promise<void> {
  await db
    .prepare(`
      INSERT INTO users (id, name, contact_email)
      VALUES (?, ?, ?)
    `)
    .bind(id, name, email) // write to NEW only
    .run();
}

export async function getUserEmail(db: D1Database, id: string): Promise<string | null> {
  const row = await db
    .prepare("SELECT contact_email FROM users WHERE id = ?") // read from NEW
    .bind(id)
    .first<{ contact_email: string }>();
  return row?.contact_email ?? null;
}
```

After the new code has been fully deployed and traffic confirmed:

```sql
-- migrations/0004_contract_drop_user_email.sql
-- SQLite does not support DROP COLUMN in older versions; use table-rebuild approach.
CREATE TABLE users_new (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  contact_email TEXT NOT NULL
);

INSERT INTO users_new SELECT id, name, contact_email FROM users;

DROP TABLE users;

ALTER TABLE users_new RENAME TO users;
```

> Note: SQLite 3.35.0+ (available in D1) supports `ALTER TABLE users DROP COLUMN user_email`
> directly. Prefer that when the column has no indexes or triggers referencing it.

```sql
-- migrations/0004_contract_drop_column.sql  (D1 / modern SQLite)
ALTER TABLE users DROP COLUMN user_email;
```

---

## Wrangler Migration Workflow

```bash
# Phase 1 — Expand
wrangler d1 migrations apply DB --env production

# Deploy Phase 1 Worker code
wrangler deploy --env production

# Phase 2 — Back-fill
wrangler d1 execute DB --env production \
  --file migrations/0003_backfill_contact_email.sql

# Verify
wrangler d1 execute DB --env production \
  --command "SELECT COUNT(*) FROM users WHERE contact_email IS NULL"

# Phase 3 — Deploy contract code first
wrangler deploy --env production

# Then apply drop migration
wrangler d1 migrations apply DB --env production
```

---

## Dealing with Multiple Worker Versions in Flight

Workers Versions (`wrangler versions upload` + gradual rollout) can briefly run Phase 1
and Phase 3 code simultaneously during a canary rollout. To guard against this:

```typescript
// Use COALESCE so Phase 3 code tolerates a back-fill race on very old rows
const row = await db
  .prepare("SELECT COALESCE(contact_email, user_email) AS email FROM users WHERE id = ?")
  .bind(id)
  .first<{ email: string }>();
```

Only remove this `COALESCE` guard after the Phase 3 migration has been 100% rolled out
and all Phase 1/2 Worker versions have drained.

---

## Anti-patterns

**Running all three phases in one deploy.** This defeats the purpose. An expand + contract in
the same migration file can leave the Worker referencing a column that was dropped in the
same transaction, causing query errors on inflight requests.

**Back-filling in application code on every read.** Lazy back-fill in the read path keeps
old rows in an inconsistent state indefinitely and makes Phase 3 unsafe to execute.

**Dropping the old column before confirming back-fill completion.** Any row where
`contact_email IS NULL` at contract time becomes a NOT NULL constraint violation or returns
null data. Always verify `COUNT(*) WHERE new_col IS NULL = 0`.

**Mixing schema migration with functional changes in the same deploy.** Keep Phase 1, 2, 3
deploys schema-only (or schema + corresponding read/write changes). Never bundle unrelated
feature work into a migration deploy.

---

## Gotchas

- D1 `migrations apply` is idempotent; re-running it is safe. But `d1 execute --file` is
  NOT tracked in the migrations table—run it manually only once.
- The table-rebuild approach in Phase 3 (for SQLite versions that lack `DROP COLUMN`) locks
  the table briefly. Schedule it during low-traffic windows.
- D1 read replicas may return rows with `contact_email = NULL` for a few seconds after the
  back-fill if the replica lags. Queries that assert `NOT NULL` at the application layer
  should use the `COALESCE` guard until Phase 3 is complete.
- Foreign key constraints referencing the old column must be recreated on the new column
  before the table-rebuild approach renames the new table.

---

## Verification Checklist

- [ ] Phase 1 migration applied; `PRAGMA table_info(users)` shows both columns.
- [ ] Worker Phase 1 code deployed; new inserts populate both columns.
- [ ] Back-fill complete: `SELECT COUNT(*) FROM users WHERE contact_email IS NULL` = 0.
- [ ] Worker Phase 3 code deployed and fully rolled out.
- [ ] Old column dropped; `PRAGMA table_info(users)` shows only `contact_email`.
- [ ] Application error rate unchanged throughout all phases.

---

## Related

- `zero-downtime-schema-migrations.md` — broader schema migration strategies
- `blue-green-database-migration-workers-d1.md` — cut-over approach using two databases
- `dual-write-problem-queues-workers.md` — risks when writing to two stores
- `optimistic-concurrency-control-d1.md` — row-level versioning during migration windows

---

## Sources

- Martin Fowler, "Parallel Change", martinfowler.com/bliki/ParallelChange.html
- SQLite ALTER TABLE docs — sqlite.org/lang_altertable.html
- Cloudflare D1 Migrations — developers.cloudflare.com/d1/reference/migrations
- Cloudflare Workers Versions — developers.cloudflare.com/workers/configuration/versions-and-deployments
