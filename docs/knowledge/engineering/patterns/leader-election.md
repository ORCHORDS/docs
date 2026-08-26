# leader-election

**Issue:** When you need a single-instance worker (cron, leader)
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a cron job that runs every 5 minutes. You deploy
your Worker to multiple regions (US, EU, APAC) for redundancy.
The cron fires 3 times (once per region). The job runs 3
times. You have a bug.

## Root cause
**Cron in CF Workers runs per-region.** If your Worker is
deployed to 3 regions, the cron fires in each region.
Without coordination, the job runs 3 times.

**Source:** CF Workers cron:
https://developers.cloudflare.com/workers/configuration/cron-triggers/

> "Cron Triggers are region-specific. ... A Worker deployed to
> multiple regions will have its Cron Trigger fire in each
> region."

## The fix: leader election

One region "wins" the cron and runs the job. The others
stand down.

### Option 1: Use a Durable Object as the leader
```ts
// One DO instance, named the same in all regions
const LEADER_ID = 'cron-leader';
const id = env.LEADER_DO.idFromName(LEADER_ID);
const stub = env.LEADER_DO.get(id);

// In the cron handler
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Acquire leadership (with a TTL)
    const acquired = await stub.fetch('https://do/acquire', {
      method: 'POST',
      body: JSON.stringify({ ttl: 240 }),  // 4 minutes (less than 5 min cron)
    });
    if (!acquired.ok) return;  // Not the leader; stand down

    try {
      await runJob(env);
    } finally {
      // Release leadership
      await stub.fetch('https://do/release', { method: 'POST' });
    }
  },
};
```

The DO's single-writer property ensures only one region
acquires leadership at a time. The TTL prevents a stuck leader
from blocking others.

### Option 2: Use a KV lock
```ts
async function tryAcquireLock(env: Env, key: string, ttlSec: number): Promise<boolean> {
  // KV doesn't have atomic lock; use a "set if not exists" pattern
  const existing = await env.KV.getWithMetadata(key);
  if (existing.value && Date.now() - existing.metadata.timestamp < ttlSec * 1000) {
    return false;  // Lock held
  }
  await env.KV.put(key, '1', {
    expirationTtl: ttlSec,
    metadata: { timestamp: Date.now() },
  });
  return true;
}

export default {
  async scheduled(event, env, ctx) {
    if (!await tryAcquireLock(env, 'cron-leader', 240)) return;
    try {
      await runJob(env);
    } finally {
      await env.KV.delete('cron-leader');
    }
  },
};
```

KV is eventually consistent, so this is not 100% reliable.
Use the DO pattern for stronger guarantees.

### Option 3: Use a database with `INSERT OR IGNORE`
```ts
// D1 has unique constraints
async function tryAcquire(env: Env, key: string, ttlSec: number): Promise<boolean> {
  const expiresAt = Date.now() + ttlSec * 1000;
  try {
    await env.DB!.prepare(
      `INSERT INTO leader_locks (id, expires_at) VALUES (?, ?)`
    ).bind(key, expiresAt).run();
    return true;  // We acquired it
  } catch (err) {
    // UNIQUE constraint failed; someone else has the lock
    // Check if the lock is expired
    const existing = await env.DB!.prepare(
      `SELECT expires_at FROM leader_locks WHERE id = ?`
    ).bind(key).first<{ expires_at: number }>();
    if (existing && existing.expires_at < Date.now()) {
      // Lock is expired; try to take it
      await env.DB!.prepare(
        `UPDATE leader_locks SET expires_at = ? WHERE id = ?`
      ).bind(expiresAt, key).run();
      return true;  // We took the expired lock
    }
    return false;  // Lock is held
  }
}
```

D1's UNIQUE constraint provides stronger guarantees than KV.

## The pattern: leader + followers

```ts
// Leader: runs the job
async function leaderRun(env: Env): Promise<void> {
  if (!await tryAcquire(env, 'job-leader', 240)) return;
  try {
    await runJob(env);
  } finally {
    await env.DB!.prepare(
      `DELETE FROM leader_locks WHERE id = ?`
    ).bind('job-leader').run();
  }
}

// Follower: waits for the leader to finish
async function followerCheck(env: Env): Promise<void> {
  // If the leader's lock has expired, the job is stuck
  // Take over and re-run
  const lock = await env.DB!.prepare(
    `SELECT expires_at FROM leader_locks WHERE id = ?`
  ).bind('job-leader').first<{ expires_at: number }>();
  if (lock && lock.expires_at < Date.now() - 30000) {
    // Leader is stuck; take over
    console.warn('Leader stuck; taking over');
    await leaderRun(env);
  }
}
```

## When to use leader election

✅ Use leader election when:
- **The job is a singleton** (e.g. database migration,
  monthly billing)
- **Multiple workers would cause bugs** (e.g. double-charge)
- **The job is idempotent** (running twice is safe)

❌ Don't use leader election when:
- **The job can be parallel** (each region runs a subset)
- **The job is per-region** (e.g. sync local cache)
- **The job is rare** (e.g. annual report)

## Verification
- **Test:** `test/leader-election.test.ts > 3 concurrent
  workers, only 1 acquires the lock` — passes
- **Test:** `test/leader-election.test.ts > leader dies, another
  worker takes over after TTL` — passes
- **Live:** The cron job runs exactly once per period

## Gotchas
- **The lock TTL is critical.** Too short = false takeover (two
  workers think they're the leader). Too long = stuck leader
  (no takeover for hours).
- **The DO pattern is the most reliable** (single-writer
  guarantee). The KV pattern is eventually consistent; the
  D1 pattern is strong but more code.
- **The lock must be re-entrant carefully.** If the leader
  crashes mid-job, the next acquirer must be able to handle
  the partial state.
- **Fencing tokens** (a monotonically increasing number with
  each lock) prevent a "zombie leader" from writing after
  losing the lock. Advanced; rarely needed.
- **For multi-region leader election**, the DO + CF's
  jurisdiction-aware routing is the standard approach.

## Related
- `per-tenant-durable-object.md` (DOs as the leader)
- `queue-system-design.md` (sagas use locks)
- `idempotency-keys.md` (essential for leader-run jobs)
- CF DOs: https://developers.cloudflare.com/durable-objects/
- CF Workflows: https://developers.cloudflare.com/workflows/
