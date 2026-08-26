# Zero-Downtime Schema Changes in D1 with the Expand-Migrate-Contract Pattern

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to rename a column, split a column into two, or add a `NOT NULL` constraint to an existing column in a live D1 database. Running a blocking `ALTER TABLE` or a multi-second backfill under traffic risks dropped requests or lock contention. You want a migration strategy that keeps the Worker serving traffic throughout.

## Context

D1 inherits SQLite's limited `ALTER TABLE` support — you cannot rename columns in older SQLite versions, change column types, or add `NOT NULL` constraints without recreating the table. The expand-migrate-contract (EMC) pattern sidesteps this by spreading the change across three phases deployed independently. Each phase is safe to run under live traffic because it avoids taking exclusive locks for long durations. D1's `batch()` API makes the DDL steps atomic, and a Workers Cron Trigger handles the background backfill without blocking request handlers.

## Expand-Migrate-Contract Pattern

```sql
-- PHASE 1: EXPAND — add the new nullable column alongside the old one
-- Deploy this migration first; both old and new columns coexist.
ALTER TABLE orders ADD COLUMN customer_email TEXT;  -- nullable, no default needed yet

-- PHASE 2 (handled by cron Worker — see below)
-- Backfill customer_email from the legacy `user_email` column in batches.

-- PHASE 3: CONTRACT — once backfill is 100 % complete:
-- SQLite cannot add NOT NULL to existing column directly.
-- Recreate the table without the old column.
CREATE TABLE orders_new (
  id             TEXT PRIMARY KEY,
  customer_email TEXT NOT NULL,
  total_cents    INTEGER NOT NULL,
  created_at     INTEGER NOT NULL
);

INSERT INTO orders_new (id, customer_email, total_cents, created_at)
  SELECT id, customer_email, total_cents, created_at FROM orders;

DROP TABLE orders;
ALTER TABLE orders_new RENAME TO orders;
```

## Atomic DDL with D1 batch()

```typescript
// migrations/run.ts  — run once via a one-off Worker or wrangler script
import { Env } from '../types';

export async function runPhase1(db: D1Database): Promise<void> {
  // batch() wraps all statements in a single transaction
  const results = await db.batch([
    db.prepare(
      `CREATE TABLE IF NOT EXISTS schema_migrations (
         name       TEXT PRIMARY KEY,
         applied_at INTEGER NOT NULL
       )`
    ),
    db.prepare(
      `INSERT OR IGNORE INTO schema_migrations (name, applied_at)
         VALUES ('phase1_add_customer_email', ?)`
    ).bind(Date.now()),
    db.prepare(
      `ALTER TABLE orders ADD COLUMN customer_email TEXT`
    ),
  ]);

  const failed = results.find((r) => !r.success);
  if (failed) throw new Error(`Migration failed: ${JSON.stringify(failed.error)}`);
  console.log('Phase 1 complete — customer_email column added');
}

export async function runPhase3(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare(
      `CREATE TABLE IF NOT EXISTS orders_new (
         id             TEXT PRIMARY KEY,
         customer_email TEXT NOT NULL,
         total_cents    INTEGER NOT NULL,
         created_at     INTEGER NOT NULL
       )`
    ),
    db.prepare(
      `INSERT INTO orders_new (id, customer_email, total_cents, created_at)
         SELECT id, customer_email, total_cents, created_at FROM orders`
    ),
    db.prepare(`DROP TABLE orders`),
    db.prepare(`ALTER TABLE orders_new RENAME TO orders`),
    db.prepare(
      `INSERT OR REPLACE INTO schema_migrations (name, applied_at)
         VALUES ('phase3_contract', ?)`
    ).bind(Date.now()),
  ]);
  console.log('Phase 3 complete — old column removed, NOT NULL enforced');
}
```

## Backfill Cron Worker (500 Rows at a Time)

```typescript
// src/cron/backfill-customer-email.ts
import { Env } from '../types';

const BATCH_SIZE = 500;

export async function backfillCustomerEmail(env: Env): Promise<void> {
  // Read the last processed offset from KV (persists across cron invocations)
  const rawOffset = await env.KV.get('backfill:customer_email:offset');
  let offset = rawOffset ? parseInt(rawOffset, 10) : 0;

  // Fetch one batch of rows that still need backfilling
  const { results } = await env.DB.prepare(
    `SELECT id, user_email
     FROM orders
     WHERE customer_email IS NULL
     LIMIT ? OFFSET ?`
  )
    .bind(BATCH_SIZE, offset)
    .all<{ id: string; user_email: string }>();

  if (results.length === 0) {
    console.log('Backfill complete — no more rows to process');
    await env.KV.put('backfill:customer_email:status', 'done');
    return;
  }

  // Build a batch update
  const stmts = results.map((row) =>
    env.DB.prepare(
      `UPDATE orders SET customer_email = ? WHERE id = ?`
    ).bind(row.user_email, row.id)
  );

  await env.DB.batch(stmts);

  offset += results.length;
  await env.KV.put('backfill:customer_email:offset', String(offset));
  console.log(`Backfilled ${offset} rows so far`);
}

// wrangler.toml:
// [[triggers]]
// crons = ["*/2 * * * *"]   # every 2 minutes
```

## Monitoring Migration Progress

```sql
-- Check how many rows still need backfilling
SELECT COUNT(*) AS remaining
FROM orders
WHERE customer_email IS NULL;

-- Check applied phases
SELECT name, datetime(applied_at / 1000, 'unixepoch') AS applied_at
FROM schema_migrations
ORDER BY applied_at;
```

## Rollback Strategy

If the backfill cron fails mid-run:

1. The `customer_email IS NULL` check means partially backfilled rows are safe — re-running the cron resumes from the stored `offset` in KV.
2. If KV state is lost, re-run with `offset = 0`; the `UPDATE … SET customer_email = ?` is idempotent for already-backfilled rows.
3. Phase 3 should only run after `remaining = 0` is confirmed. Gate Phase 3 behind a manual check or a separate migration flag in `schema_migrations`.
4. To abort entirely before Phase 3: `ALTER TABLE orders DROP COLUMN customer_email;` (supported in SQLite 3.35+ / D1).

## Anti-patterns

- **Single-transaction backfill** — Running `UPDATE orders SET customer_email = user_email` in one shot locks the table for seconds or minutes under load.
- **Skipping Phase 1** — Deploying Phase 3 directly causes `NOT NULL` violations for rows written between deploy and backfill completion.
- **Hardcoding offsets** — Storing the offset in the Worker's global scope resets on every cold start; always persist it in KV or D1.

## Gotchas

- D1's `batch()` is atomic per call but does not span across multiple `batch()` invocations in the cron.
- `ALTER TABLE … RENAME TO` acquires a brief exclusive lock; run it during low-traffic windows.
- D1 does not support `ALTER TABLE … DROP COLUMN` in all runtime versions; test in your target environment first.
- The `OFFSET` pattern is O(n) in SQLite; for very large tables prefer a cursor on `id > last_seen_id`.

## Verification

```bash
# Check remaining rows after a few cron runs
wrangler d1 execute example project-db \
  --command "SELECT COUNT(*) FROM orders WHERE customer_email IS NULL;"

# Confirm schema_migrations table state
wrangler d1 execute example project-db \
  --command "SELECT * FROM schema_migrations ORDER BY applied_at;"

# After Phase 3, verify the new schema
wrangler d1 execute example project-db \
  --command "PRAGMA table_info(orders);"
```

## Related

- `d1-partial-index-conditional-expressions-workers.md`
- `d1-row-versioning-optimistic-locking-workers.md`
- `d1-generated-columns-computed-fields-workers.md`

## Sources

- Cloudflare D1 Migrations — https://developers.cloudflare.com/d1/reference/migrations/
- SQLite ALTER TABLE — https://www.sqlite.org/lang_altertable.html
- Expand/Contract Pattern — https://openpracticelibrary.com/practice/expand-contract-pattern/
