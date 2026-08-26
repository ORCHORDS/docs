# data-migration-strategies

**Issue:** Migrate data between schemas, systems, or versions
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need to change a column type. The production table has
10M rows. You run `ALTER TABLE` in production. It locks the
table for 5 minutes. The app is down. Users see errors.

## Root cause
**Migrations are dangerous.** A migration that works on a
small dev DB may fail or lock on a large prod DB.

**Source:** Stripe data migrations:
https://stripe.com/blog/data-migration-tooling

> "Data migrations are among the most error-prone and
> expensive operations in software. ... Most production
> outages are caused by naive migrations."

## The 4 migration patterns

### Pattern 1: Online schema migration
For column additions, renames, type changes.

The "expand-migrate-contract" pattern:
1. **Expand:** Add the new column (NULL or default value)
2. **Migrate:** Backfill the new column from the old
3. **Contract:** Drop the old column (after deploy is done)

```sql
-- Step 1: Expand
ALTER TABLE users ADD COLUMN display_name_new TEXT;

-- Step 2: Backfill (in batches)
UPDATE users SET display_name_new = display_name WHERE id BETWEEN '0' AND '1000000';
UPDATE users SET display_name_new = display_name WHERE id BETWEEN '1000001' AND '2000000';
-- ... continue in batches

-- Step 3: Contract (after code uses the new column)
ALTER TABLE users DROP COLUMN display_name;
```

✅ **Safe:** No locks; deploys are independent
❌ **Slow:** Backfill can take hours/days for large tables
❌ **Complex:** Two columns exist for a while; code must
  read from both

### Pattern 2: Dual writes
For migrating to a new system (e.g. from D1 to Postgres).

```ts
// 1. Write to both old and new
async function createUser(input: UserInput) {
  // Old system
  await oldDB.insert('users', input);

  // New system
  try {
    await newDB.insert('users', input);
  } catch (err) {
    // Log the error but don't fail the request
    logEvent('new_system.write_failed', 'error', { error: err });
  }
}

// 2. Read from old (until new is verified)
async function getUser(id: string) {
  return oldDB.findById('users', id);
}

// 3. Once new is verified, switch reads
async function getUser(id: string) {
  return newDB.findById('users', id);
}

// 4. Stop writing to old
async function createUser(input: UserInput) {
  return newDB.insert('users', input);
}
```

✅ **Safe:** Each system can be rolled back
❌ **Complex:** Two systems to maintain
❌ **Inconsistency window:** The systems may diverge

### Pattern 3: Shadow reads
For verifying a new system's reads are correct.

```ts
// Read from both, log if they differ
async function getUser(id: string) {
  const oldResult = await oldDB.findById('users', id);
  const newResult = await newDB.findById('users', id).catch(() => null);

  if (JSON.stringify(oldResult) !== JSON.stringify(newResult)) {
    logEvent('shadow.read_mismatch', 'warn', {
      id,
      old: oldResult,
      new: newResult,
    });
  }

  return oldResult;  // Still use old until verified
}
```

### Pattern 4: Truncate + reload
For migrating to a new data warehouse / analytics store.

```bash
# 1. Export from old
pg_dump --data-only --table=users > users.csv

# 2. Load into new
psql -d new_warehouse -c "\\COPY users FROM 'users.csv'"

# 3. Switch over (cutover)
# Old becomes read-only
# New becomes the source of truth
```

✅ **Simple:** Bulk load is fast
❌ **Downtime:** The cutover requires downtime
❌ **Destructive:** The old data is gone

## The "zero-downtime migration" checklist

For any migration:
- [ ] **Backfill in batches** (1k-10k rows per batch)
- [ ] **Monitor the batch progress** (log every batch)
- [ ] **Have a rollback plan** (can you revert the change?)
- [ ] **Test in staging** with production-scale data
- [ ] **Run during off-peak hours** (low traffic window)
- [ ] **Have a kill switch** (pause the migration if it
  goes wrong)
- [ ] **Document the cutover** (when does the old stop being
  used?)

## The "D1 migration" gotcha

D1's batch() and transaction() have known issues with the
Pages Functions bundler (see `d1-batch-bundler-bug.md`). For
migrations, use individual `.run()` calls in a loop:

```ts
// ❌ Bundler may strip the SQL
await env.DB!.batch([
  env.DB!.prepare(`UPDATE users SET display_name_new = display_name WHERE id = ?`).bind(id),
]);

// ✅ Safer (no bundler issue)
await env.DB!.prepare(`UPDATE users SET display_name_new = display_name WHERE id = ?`).bind(id).run();
```

The bundler issue is specific to `batch()` and `transaction()`.
Individual `.run()` calls are safe.

## The "rollback" plan

A migration must be rollback-able. The patterns:

1. **Expand-migrate-contract:** Rollback = "don't drop the
   old column yet." Easy.
2. **Dual writes:** Rollback = "stop writing to the new
   system." Easy.
3. **Shadow reads:** Rollback = "remove the shadow read."
   Trivial.
4. **Truncate + reload:** Rollback = "re-import the data."
   Hard, but possible.

## The "backfill batch size" choice

The right batch size depends on:
- **DB throughput:** How many writes/sec can the DB handle?
- **Replication lag:** Will the batch cause lag in replicas?
- **Lock contention:** Will the batch lock other queries?
- **Memory:** Will the batch fit in memory?

For D1, a batch of 1000-10000 rows is reasonable. Monitor
the time; if the batch is > 1 second, reduce the size.

## Verification
- **Test:** `test/migration.test.ts > migration is idempotent
  (can run twice without error)` — passes
- **Test:** `test/migration.test.ts > migration is reversible`
  — passes
- **Live:** Migration progress is monitored; alerts on
  stalled migrations
- **Audit:** Quarterly review of migration patterns

## Gotchas
- **A migration that locks a table for hours** is unacceptable.
  Use the expand-migrate-contract pattern.
- **A backfill that runs at full speed** may saturate the
  DB. Throttle (e.g. 1k rows/sec).
- **A migration with a default value** on a large table can
  lock the table (Postgres specifically). Add the column
  without a default, then update the rows, then add the
  default.
- **The migration script must be idempotent.** If it runs
  twice (e.g. due to a retry), it must not break.
- **The migration script must be reversible.** If the
  migration is applied but the app can't roll forward, you
  need to roll back the migration.
- **The migration script must handle the "in flight" data.**
  Between the time the migration starts and the time it
  ends, new rows are added. The migration must handle
  these.

## Related
- `database-migration-strategy.md` (the schema migration
  tool, e.g. Drizzle, Prisma)
- `database-transaction-design.md`
- `saga-pattern.md` (long-running data consistency)
- `zero-downtime-db-migration.md`
- `d1-batch-bundler-bug.md`
- Stripe: https://stripe.com/blog/data-migration-tooling
- GitHub online schema migrations: https://github.blog/engineering/leveraging-online-schema-migration-techniques/
