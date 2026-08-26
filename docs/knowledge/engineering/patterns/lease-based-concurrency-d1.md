# Lease-based Concurrency Control with D1

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A background job, cron trigger, or queue consumer should run on exactly one Worker
instance at a time, but Durable Objects are unavailable (budget, architecture, or a
desire to keep all state in D1). Multiple Workers start concurrently, all query the
same job table, and duplicate work: emails sent twice, invoices doubled, inventory
decremented multiple times.

A **lease** stored in D1 acts as a lightweight distributed lock using an atomic SQL
`UPDATE … WHERE expires_at < now()` that only one writer can win.

## Context

D1 is a globally-replicated SQLite database; writes go to the primary and are
synchronised to read replicas. Reads in the same region as the primary are strongly
consistent; cross-region reads may lag by a few milliseconds. For lease acquisition
the write must go to the primary (`cf: { d1: { primary: true } }`) to avoid
read-your-writes races.

The lease table stores: which worker holds the lease (`owner`), when it expires
(`expires_at`), and optionally what work item is locked (`resource_id`). An `UPDATE`
with a `WHERE expires_at < ?` clause makes acquisition atomic — SQLite processes the
statement as a single operation with no gap between read and write.

## Schema and Migrations

```sql
-- migrations/0001_create_leases.sql
CREATE TABLE IF NOT EXISTS leases (
  resource_id TEXT     NOT NULL,
  owner       TEXT     NOT NULL DEFAULT '',
  expires_at  INTEGER  NOT NULL DEFAULT 0,  -- Unix ms
  version     INTEGER  NOT NULL DEFAULT 0,
  PRIMARY KEY (resource_id)
);

-- Seed rows for known resources so UPDATE (not INSERT) wins the race.
-- The seed row represents "no lease held" (expires_at = 0 < any real timestamp).
INSERT OR IGNORE INTO leases (resource_id, owner, expires_at, version)
VALUES ('billing-cron', '', 0, 0);
```

## Acquiring and Renewing a Lease

```typescript
// lease.ts
export interface LeaseOptions {
  resourceId: string;
  owner:      string;  // e.g. crypto.randomUUID() per Worker invocation
  ttlMs:      number;  // how long the lease is valid (e.g. 60_000)
}

export interface LeaseResult {
  acquired: boolean;
  expiresAt?: number;
  version?:   number;
}

export async function acquireLease(
  db:   D1Database,
  opts: LeaseOptions
): Promise<LeaseResult> {
  const now       = Date.now();
  const expiresAt = now + opts.ttlMs;

  // Atomic acquire: only succeeds if the row is expired (or never held)
  const result = await db
    .prepare(`
      UPDATE leases
      SET    owner      = ?,
             expires_at = ?,
             version    = version + 1
      WHERE  resource_id = ?
        AND  expires_at  < ?
    `)
    .bind(opts.owner, expiresAt, opts.resourceId, now)
    .run();

  if (result.meta.changes === 1) {
    // Read back the version we just wrote
    const row = await db
      .prepare("SELECT version FROM leases WHERE resource_id = ?")
      .bind(opts.resourceId)
      .first<{ version: number }>();
    return { acquired: true, expiresAt, version: row?.version };
  }

  return { acquired: false };
}

export async function renewLease(
  db:      D1Database,
  opts:    LeaseOptions,
  version: number   // must match the version we hold
): Promise<boolean> {
  const expiresAt = Date.now() + opts.ttlMs;

  const result = await db
    .prepare(`
      UPDATE leases
      SET    expires_at = ?,
             version    = version + 1
      WHERE  resource_id = ?
        AND  owner       = ?
        AND  version     = ?
    `)
    .bind(expiresAt, opts.resourceId, opts.owner, version)
    .run();

  return result.meta.changes === 1;
}

export async function releaseLease(
  db:   D1Database,
  opts: Pick<LeaseOptions, "resourceId" | "owner">
): Promise<void> {
  await db
    .prepare(`
      UPDATE leases
      SET    owner      = '',
             expires_at = 0
      WHERE  resource_id = ?
        AND  owner       = ?
    `)
    .bind(opts.resourceId, opts.owner)
    .run();
}
```

## Running a Job Under a Lease

```typescript
// billing-cron.ts
import { acquireLease, renewLease, releaseLease } from "./lease";

const RESOURCE  = "billing-cron";
const TTL_MS    = 55_000;  // slightly less than cron interval (60 s)
const RENEW_MS  = 20_000;  // renew every 20 s while working

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const owner = crypto.randomUUID();

    const lease = await acquireLease(env.DB, {
      resourceId: RESOURCE,
      owner,
      ttlMs: TTL_MS,
    });

    if (!lease.acquired) {
      // Another Worker is already running — skip silently
      console.log(`[billing-cron] lease busy, skipping`);
      return;
    }

    let version     = lease.version!;
    let renewHandle: ReturnType<typeof setInterval> | null = null;

    try {
      // Keep-alive: renew the lease while processing
      renewHandle = setInterval(async () => {
        const ok = await renewLease(env.DB, { resourceId: RESOURCE, owner, ttlMs: TTL_MS }, version);
        if (ok) {
          version++;
        } else {
          // Lost the lease (e.g. another worker stole after apparent expiry)
          console.error("[billing-cron] lost lease mid-run — stopping");
          // Signal the main loop to abort (set a flag on a shared object or throw)
        }
      }, RENEW_MS);

      await runBillingCycle(env);
    } finally {
      if (renewHandle) clearInterval(renewHandle);
      await releaseLease(env.DB, { resourceId: RESOURCE, owner });
    }
  },
};

async function runBillingCycle(env: Env): Promise<void> {
  // Fetch un-billed subscriptions in batches and process them
  const batch = await env.DB
    .prepare("SELECT id FROM subscriptions WHERE billed_at IS NULL LIMIT 100")
    .all<{ id: string }>();

  for (const row of batch.results) {
    await chargeSubscription(env, row.id);
  }
}
```

## Handling Stale Leases and Race Conditions

```typescript
// Diagnostics endpoint: show current lease holder
export async function leaseStatusHandler(
  request: Request,
  env: Env
): Promise<Response> {
  const url        = new URL(request.url);
  const resourceId = url.searchParams.get("resource") ?? RESOURCE;

  const row = await env.DB
    .prepare("SELECT owner, expires_at, version FROM leases WHERE resource_id = ?")
    .bind(resourceId)
    .first<{ owner: string; expires_at: number; version: number }>();

  if (!row) return new Response("Unknown resource", { status: 404 });

  const now  = Date.now();
  const held = row.expires_at > now;

  return Response.json({
    resourceId,
    held,
    owner:       held ? row.owner : null,
    expiresAt:   held ? new Date(row.expires_at).toISOString() : null,
    ttlRemaining: held ? row.expires_at - now : 0,
    version:     row.version,
  });
}
```

## Anti-patterns

- **Using `SELECT` then `UPDATE` in two statements**: a gap between read and write
  allows two Workers to both read "no lease held" and both proceed to write. The
  entire acquire must be a single `UPDATE … WHERE expires_at < now()`.
- **Leases without renewal**: a job that takes longer than the TTL will have its
  lease stolen by a competing Worker mid-execution. Either use a shorter-than-expected
  TTL with periodic renewal or set TTL generously above the worst-case run time.
- **Reading from a read replica for lease checks**: cross-region read replicas can
  lag. Always route lease writes (and ideally reads) through the D1 primary binding.
- **Setting TTL equal to the cron interval**: a previous run that finishes at the
  last second blocks the next scheduled invocation. Use TTL slightly shorter than the
  cron period, or release immediately on completion.
- **Not seeding the lease row**: if the row is missing, `UPDATE` affects 0 rows and
  every Worker thinks the lease is "not acquired". Seed on migration.

## Gotchas

- **D1 `meta.changes`**: always check `result.meta.changes === 1` after an UPDATE
  to confirm the conditional write succeeded. Do not assume success from lack of error.
- **Clock skew**: Worker instances may have small clock differences (< 1 s). Use
  generous TTLs (≥ 30 s) to make skew irrelevant.
- **`setInterval` in Workers**: the Workers runtime does not natively support
  `setInterval` during `scheduled()` handler execution without holding open the
  execution context. Use `ctx.waitUntil(renewLoop())` where `renewLoop` is an async
  loop with `await scheduler.wait(RENEW_MS)` between iterations.
- **D1 write limits**: D1 has per-database write throughput limits. High-frequency
  lease renewals from many Workers can exhaust the write budget. Tune RENEW_MS.
- **Version counter overflow**: a 64-bit SQLite integer overflows after 9.2 × 10¹⁸
  increments — practically never, but use `INTEGER` not `TEXT` to keep comparisons fast.

## Verification

```bash
# Confirm atomic acquire: fire 5 concurrent cron-equivalent requests
for i in $(seq 1 5); do
  curl -s "https://your-worker.dev/trigger-billing" &
done
wait

# Exactly one should log "lease acquired"; others "lease busy, skipping"
# Check lease table via D1 console or wrangler d1 execute:
npx wrangler d1 execute your-db --command \
  "SELECT resource_id, owner, datetime(expires_at/1000,'unixepoch') as exp, version FROM leases"

# Simulate expired lease: set expires_at to the past
npx wrangler d1 execute your-db --command \
  "UPDATE leases SET expires_at = 1 WHERE resource_id = 'billing-cron'"
# Next invocation should acquire successfully
```

## Related

- `distributed-lock-durable-objects.md` — stronger consistency via DO (no D1 replication lag)
- `idempotency-key-pattern-workers-d1.md` — per-operation idempotency in D1
- `cron-scheduling.md` — scheduling patterns for Cloudflare Workers
- `database-transaction-design.md` — D1 transaction isolation semantics

## Sources

- Cloudflare D1 documentation — write consistency and primary routing
  https://developers.cloudflare.com/d1/build-with-d1/d1-and-prisma/
- SQLite documentation — UPDATE with WHERE as atomic test-and-set
  https://www.sqlite.org/lang_update.html
- Martin Fowler, "Patterns of Enterprise Application Architecture" — Optimistic
  Locking / Pessimistic Locking
