# D1 Schema Migration Table Lock Peak Traffic Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

On 2026-08-04 at 09:15 UTC (peak EU traffic), a `wrangler d1 migrations apply` run for the example project production database executed an `ALTER TABLE workspaces ADD COLUMN billing_tier TEXT` migration. D1 acquired a write lock for 18 seconds during the migration. All concurrent `INSERT` and `UPDATE` statements against `workspaces` returned `SQLITE_BUSY` and timed out. The `GET /api/workspaces/:id` endpoint degraded for 31 seconds (lock duration + retry backoff). 1,240 requests failed with HTTP 500.

## Context

D1 runs on SQLite under the hood. Schema-altering DDL statements (`ALTER TABLE`, `CREATE INDEX`, `DROP COLUMN`) acquire an exclusive write lock for the duration of execution. example project engineers assumed D1 migrations were near-instant for a small `workspaces` table (12,000 rows), but the lock contention at peak traffic — not the migration duration itself — caused the degradation. The deploy pipeline had no traffic-aware deploy gate.

---

## Section 1: The Root Cause — Synchronous DDL Under Write Load

```sql
-- migration 0021_add_billing_tier.sql
-- Ran at peak traffic; holds exclusive write lock during ALTER
ALTER TABLE workspaces ADD COLUMN billing_tier TEXT NOT NULL DEFAULT 'free';
```

SQLite's `ALTER TABLE ADD COLUMN` is normally fast, but under D1's multi-tenant isolation layer, even brief write locks compound when hundreds of Workers are concurrently writing to the same table.

---

## Section 2: Migrate During Low-Traffic Windows With a Deploy Gate

Add a traffic-aware gate in the CI/CD pipeline that blocks schema migrations outside a declared maintenance window.

```typescript
// scripts/migration-gate.ts — called before wrangler d1 migrations apply
const ALLOWED_HOURS_UTC = [2, 3, 4, 5]; // 02:00–05:59 UTC

async function assertMigrationWindow(): Promise<void> {
  const hourUtc = new Date().getUTCHours();

  if (!ALLOWED_HOURS_UTC.includes(hourUtc)) {
    console.error(
      `Schema migration blocked outside maintenance window.\n` +
      `Current UTC hour: ${hourUtc}. Allowed: ${ALLOWED_HOURS_UTC.join(', ')}.\n` +
      `To override: set FORCE_MIGRATION=true in CI (requires on-call approval).`
    );
    if (process.env.FORCE_MIGRATION !== 'true') {
      process.exit(1);
    }
    console.warn('[migration-gate] Override active — proceeding outside window.');
  }
}

await assertMigrationWindow();
```

---

## Section 3: Non-Locking Column Addition With Default Via Application Layer

For additive changes, avoid `NOT NULL DEFAULT` constraints on large tables — they require a full table rewrite in SQLite. Use a nullable column and handle defaults in the application.

```sql
-- PREFERRED for large tables: nullable column, no DEFAULT at DDL level
-- migration 0021_add_billing_tier_nullable.sql
ALTER TABLE workspaces ADD COLUMN billing_tier TEXT;
```

```typescript
// workspace-repository.ts — application-layer default
async function getWorkspace(id: string, env: Env): Promise<Workspace> {
  const row = await env.DB.prepare(
    'SELECT *, COALESCE(billing_tier, ?) AS billing_tier FROM workspaces WHERE id = ?'
  ).bind('free', id).first<WorkspaceRow>();

  if (!row) throw new Error(`Workspace not found: ${id}`);
  return row;
}
```

After a safe deploy window, backfill the column:

```sql
-- migration 0022_backfill_billing_tier.sql — run in low-traffic window, batched
UPDATE workspaces SET billing_tier = 'free' WHERE billing_tier IS NULL AND rowid BETWEEN ? AND ?;
```

---

## Section 4: Batched Backfill Worker to Avoid Write Storms

Run backfills as a Cron Trigger Worker in small batches to avoid locking the table for the full backfill duration.

```typescript
// backfill-billing-tier.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const BATCH_SIZE = 500;
    const DELAY_MS   = 200;

    let offset = 0;
    let updated = 0;

    do {
      const result = await env.DB.prepare(`
        UPDATE workspaces
        SET billing_tier = 'free'
        WHERE billing_tier IS NULL
        LIMIT ${BATCH_SIZE}
      `).run();

      updated = result.meta.changes ?? 0;
      offset += updated;

      if (updated > 0) {
        await new Promise(r => setTimeout(r, DELAY_MS));
      }
    } while (updated === BATCH_SIZE);

    console.log(`[backfill] billing_tier backfill complete. Total updated: ${offset}`);
  },
};
```

---

## Section 5: Read-Path Resilience During Migrations

Add a circuit breaker in the data access layer to return stale cache data when D1 returns `SQLITE_BUSY`.

```typescript
// workspace-repository.ts — SQLITE_BUSY fallback
const SQLITE_BUSY_CODE = 'SQLITE_BUSY';

async function getWorkspaceWithFallback(
  id: string,
  env: Env,
  ctx: ExecutionContext
): Promise<Workspace | null> {
  try {
    return await getWorkspace(id, env);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (message.includes(SQLITE_BUSY_CODE)) {
      console.warn(`[D1] SQLITE_BUSY for workspace ${id} — serving KV fallback`);
      const cached = await env.example project_CACHE.get(`v2:tenant:${id}:workspace`, 'json');
      return cached as Workspace | null;
    }
    throw err;
  }
}
```

Pre-warm the KV fallback cache on every successful read so it is always available:

```typescript
ctx.waitUntil(
  env.example project_CACHE.put(`v2:tenant:${id}:workspace`, JSON.stringify(workspace), {
    expirationTtl: 120,
  })
);
```

---

## Anti-patterns

- Running DDL migrations against production D1 during peak traffic hours without a deployment gate.
- Using `ALTER TABLE ADD COLUMN ... NOT NULL DEFAULT value` on tables with significant write concurrency — triggers a full table rewrite in SQLite.
- Backfilling millions of rows in a single unbatched `UPDATE` — holds the write lock for the entire backfill duration.
- Assuming D1 migration duration equals D1 lock contention duration — even fast DDL causes cascading `SQLITE_BUSY` under concurrent write load.

## Gotchas

- D1 does not yet support `NOWAIT` or `SKIP LOCKED` — `SQLITE_BUSY` is the only signal that lock contention occurred.
- `wrangler d1 migrations apply` executes migrations synchronously in the calling process; it does not drain existing requests first.
- Adding a column with `DEFAULT` in SQLite ≥3.37 is fast (stored metadata only), but `NOT NULL DEFAULT` with a non-constant value still rewrites the table.
- D1 Time Travel cannot undo a DDL migration cleanly if rows were written between the migration and the rollback bookmark — always test rollback timing.

## Verification

1. Shadow-test the migration on a staging D1 instance loaded with production-scale row counts under synthetic write load; measure lock hold time.
2. Confirm `migration-gate.ts` blocks the deploy at the CI step when run outside the maintenance window.
3. After deploying the nullable column, query `SELECT COUNT(*) FROM workspaces WHERE billing_tier IS NULL` to confirm backfill progress.
4. Alert: D1 `SQLITE_BUSY` error rate > 0.1% over 1-minute window → PagerDuty P1 (schema migration likely in progress).

## Related

- `d1-migration-rollback-failed-production-lesson.md`
- `d1-write-contention-viral-event-postmortem.md`
- `d1-foreign-key-constraint-migration-production-outage.md`
- `d1-batch-size-limit-exceeded-postmortem.md`
- `migrations-must-be-backward-compatible.md`
- `monitor-before-and-after-deploy.md`

## Sources

- SQLite ALTER TABLE documentation — Column addition constraints: https://www.sqlite.org/lang_altertable.html
- Cloudflare D1 documentation — Migrations: https://developers.cloudflare.com/d1/reference/migrations/
- Cloudflare D1 documentation — Time Travel: https://developers.cloudflare.com/d1/reference/time-travel/
- example project incident ticket INC-2026-0804-D1-LOCK
