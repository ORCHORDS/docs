# D1 Advisory Lock Pattern for Coordinating Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Multiple Cloudflare Worker instances — cron triggers, queue consumers, or concurrent API handlers — must not execute a critical section simultaneously (e.g. sending a digest email, running a migration, or claiming a work item). PostgreSQL's `pg_advisory_lock` has no equivalent in D1/SQLite, and D1 does not expose serialisable multi-statement transactions across HTTP requests.

## Context

SQLite serialises all writes through a single write lock at the storage layer, but D1's HTTP API exposes each `run()` call as an independent transaction — there is no "hold a lock across requests" primitive. The standard workaround is an "optimistic advisory lock table": a row with a `locked_by` token, `locked_at` timestamp, and a short TTL. A Worker claims the lock by attempting a conditional UPDATE that only succeeds if the lock is free or expired; the affected-rows count (`meta.changes`) determines whether the claim succeeded. This pattern works because D1 serialises concurrent writes and `meta.changes === 1` is an atomic confirmation. For true distributed mutual exclusion across many Workers consider Durable Objects instead; this pattern suits low-frequency critical sections (cron jobs, one-off ops) with TTLs measured in minutes.

## Schema

```sql
-- migrations/0018_advisory_locks.sql
CREATE TABLE IF NOT EXISTS advisory_locks (
  lock_name   TEXT    NOT NULL PRIMARY KEY,
  locked_by   TEXT,                            -- worker invocation ID or UUID
  locked_at   TEXT,                            -- ISO 8601
  expires_at  TEXT,                            -- ISO 8601; NULL = not held
  holder_meta TEXT                             -- JSON: any debugging context
);

-- Pre-seed the locks your application uses so the row always exists
INSERT OR IGNORE INTO advisory_locks (lock_name) VALUES
  ('digest_email_sender'),
  ('schema_migration_runner'),
  ('nightly_report_generator');
```

## Acquiring and Releasing the Lock

```typescript
// src/advisory-lock.ts
import type { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
}

export interface LockHandle {
  lockName: string;
  lockId: string;
  release: () => Promise<void>;
}

// Try to acquire; returns null if lock is held by another worker
export async function acquireLock(
  db: D1Database,
  lockName: string,
  ttlSeconds = 120,
  meta?: Record<string, unknown>
): Promise<LockHandle | null> {
  const lockId = crypto.randomUUID();
  const now    = new Date().toISOString();
  const exp    = new Date(Date.now() + ttlSeconds * 1000).toISOString();

  // Claim the lock only if:
  //   - it is not currently held (expires_at IS NULL), OR
  //   - the current lock has expired
  const result = await db.prepare(
    `UPDATE advisory_locks
     SET
       locked_by   = ?2,
       locked_at   = ?3,
       expires_at  = ?4,
       holder_meta = ?5
     WHERE lock_name  = ?1
       AND (expires_at IS NULL OR expires_at < ?3)`
  )
    .bind(lockName, lockId, now, exp, JSON.stringify(meta ?? {}))
    .run();

  if ((result.meta.changes ?? 0) === 0) {
    // Lock is held; return null so caller can bail out gracefully
    return null;
  }

  return {
    lockName,
    lockId,
    release: () => releaseLock(db, lockName, lockId),
  };
}

// Release the lock — only if we still own it (prevent stale release)
async function releaseLock(
  db: D1Database,
  lockName: string,
  lockId: string
): Promise<void> {
  await db.prepare(
    `UPDATE advisory_locks
     SET locked_by = NULL, locked_at = NULL, expires_at = NULL, holder_meta = NULL
     WHERE lock_name = ?1 AND locked_by = ?2`
  )
    .bind(lockName, lockId)
    .run();
}
```

## Using the Lock in a Cron Handler

```typescript
// src/digest.ts
import type { ScheduledEvent, ExecutionContext } from '@cloudflare/workers-types';
import { acquireLock } from './advisory-lock';

interface Env {
  DB: D1Database;
}

async function sendDigestEmails(env: Env): Promise<void> {
  // ... actual email sending logic
  const { results } = await env.DB.prepare(
    `SELECT user_id, email FROM users
     WHERE digest_opt_in = 1
       AND last_digest_at < datetime('now', '-23 hours')`
  ).all<{ user_id: number; email: string }>();

  for (const user of results) {
    // send email, update last_digest_at ...
    await env.DB.prepare(
      `UPDATE users SET last_digest_at = datetime('now') WHERE user_id = ?`
    ).bind(user.user_id).run();
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const lock = await acquireLock(env.DB, 'digest_email_sender', 300, {
      worker: 'digest-cron',
      startedAt: new Date().toISOString(),
    });

    if (!lock) {
      console.log('digest_email_sender lock held by another worker — skipping this run');
      return;
    }

    // Extend the Workers invocation beyond the scheduled handler lifetime
    ctx.waitUntil(
      (async () => {
        try {
          await sendDigestEmails(env);
        } finally {
          await lock.release();   // always release, even on error
        }
      })()
    );
  },
};
```

## Querying Lock State and Detecting Stale Locks

```typescript
// src/lock-admin.ts

interface LockStatus {
  lock_name: string;
  is_held: boolean;
  locked_by: string | null;
  locked_at: string | null;
  expires_at: string | null;
  is_expired: boolean;
  holder_meta: Record<string, unknown> | null;
}

export async function getLockStatuses(env: Env): Promise<LockStatus[]> {
  const { results } = await env.DB.prepare(
    `SELECT
       lock_name,
       locked_by,
       locked_at,
       expires_at,
       holder_meta,
       CASE WHEN expires_at IS NOT NULL AND expires_at < datetime('now')
            THEN 1 ELSE 0 END AS is_expired,
       CASE WHEN expires_at IS NOT NULL AND expires_at >= datetime('now')
            THEN 1 ELSE 0 END AS is_held
     FROM advisory_locks
     ORDER BY lock_name`
  ).all<{
    lock_name: string;
    locked_by: string | null;
    locked_at: string | null;
    expires_at: string | null;
    holder_meta: string | null;
    is_expired: number;
    is_held: number;
  }>();

  return results.map(r => ({
    lock_name:   r.lock_name,
    is_held:     r.is_held === 1,
    locked_by:   r.locked_by,
    locked_at:   r.locked_at,
    expires_at:  r.expires_at,
    is_expired:  r.is_expired === 1,
    holder_meta: r.holder_meta ? JSON.parse(r.holder_meta) : null,
  }));
}

// Force-clear a stale lock (admin use only)
export async function forceReleaseLock(env: Env, lockName: string): Promise<void> {
  await env.DB.prepare(
    `UPDATE advisory_locks
     SET locked_by = NULL, locked_at = NULL, expires_at = NULL, holder_meta = NULL
     WHERE lock_name = ?`
  ).bind(lockName).run();
}
```

## Anti-patterns

- Setting an extremely long TTL (e.g. 24 hours) — if a Worker crashes mid-job the lock stays held for a day, blocking all subsequent runs. Keep TTL just above worst-case job duration.
- Relying on this pattern for sub-second mutual exclusion across many concurrent Worker instances — the D1 write serialisation adds tens of milliseconds of latency; use Durable Objects or a KV-backed lock for high-frequency contention.
- Not calling `lock.release()` in a `finally` block — any uncaught exception will leave the lock held until TTL expiry; the `try/finally` pattern is mandatory.

## Gotchas

- D1's `meta.changes` reflects rows changed by the last statement; in a `batch()` call only the last statement's meta is returned. Issue the lock claim as a standalone `.run()` call so you can inspect its `meta.changes` independently.
- Workers Cron invocations can overlap if the previous run exceeds the cron interval — always implement the lock even for supposedly "one at a time" cron jobs.
- The `UPDATE ... WHERE expires_at < ?` comparison relies on ISO 8601 string collation (`datetime('now')` output is always `YYYY-MM-DD HH:MM:SS`), which sorts correctly lexicographically. Using a non-ISO format for stored timestamps breaks the expiry comparison.

## Verification

```bash
# Seed the lock row
wrangler d1 execute MY_DB --remote \
  --command "INSERT OR IGNORE INTO advisory_locks (lock_name) VALUES ('test_lock');"

# Simulate acquiring
wrangler d1 execute MY_DB --remote \
  --command "UPDATE advisory_locks
             SET locked_by='worker-abc', locked_at=datetime('now'), expires_at=datetime('now','+2 minutes')
             WHERE lock_name='test_lock' AND (expires_at IS NULL OR expires_at < datetime('now'));"

# Confirm meta.changes = 1 (first acquire) vs 0 (already held)
wrangler d1 execute MY_DB --remote \
  --command "SELECT locked_by, expires_at FROM advisory_locks WHERE lock_name='test_lock';"
```

## Related

- `database/advisory-locks-postgres.md`
- `database/job-queue-skip-locked.md`
- `database/idempotency-keys-database.md`
- `database/d1-materialized-view-simulation-cron.md`
- `database/d1-batch-operations-performance.md`

## Sources

- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://developers.cloudflare.com/durable-objects/ (alternative for high-frequency locking)
- https://www.sqlite.org/isolation.html
