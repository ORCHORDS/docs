# Lease-Based Distributed Lock with D1 CAS

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Multiple Workers instances race to process the same resource — a scheduled job
that must run exactly once, a write that must not be concurrent, or a
leader-election slot. You need a distributed lock that:

- Automatically expires if the holder crashes
- Is safe under network partitions (no split-brain)
- Works without Durable Objects (which require state routing)
- Uses existing D1 infrastructure

---

## Context

A **lease** is a time-bounded lock: the holder must renew it within a TTL or it
expires and another worker can acquire it. Compare-And-Swap (CAS) on D1 is the
safe acquisition primitive — `UPDATE … WHERE holder IS NULL AND expires_at < now()`
returns 0 rows on contention, 1 row on success, atomically.

D1 runs SQLite with serialised writes per database, giving single-writer
semantics suitable for leader election and rate-limiting critical sections.

```
Worker A          D1 (leases table)        Worker B
  │                      │                    │
  ├─ INSERT/UPDATE CAS ──►│                    │
  │◄─ 1 row changed ──────│                    │
  │  (lock acquired)      │                    │
  │                       │◄─ CAS attempt ─────┤
  │                       │─ 0 rows changed ──►│
  │  [work…]              │  (contended)       │
  │                       │                    │
  ├─ UPDATE renew ────────►│                    │
  │                       │                    │
  ├─ DELETE release ───────►│                    │
```

---

## Schema

```sql
CREATE TABLE IF NOT EXISTS distributed_leases (
  resource_id  TEXT PRIMARY KEY,
  holder_id    TEXT NOT NULL,
  acquired_at  TEXT NOT NULL,
  expires_at   TEXT NOT NULL,
  version      INTEGER NOT NULL DEFAULT 0
);

-- Index for expiry scans
CREATE INDEX IF NOT EXISTS idx_leases_expires
  ON distributed_leases (expires_at);
```

---

## Acquire — CAS Insert/Update

```typescript
import { nanoid } from "nanoid";

interface Env {
  DB: D1Database;
}

interface LeaseAcquireResult {
  acquired: boolean;
  holderId: string | null;
  expiresAt: string | null;
}

const LEASE_TTL_SECONDS = 30;

async function acquireLease(
  db: D1Database,
  resourceId: string
): Promise<LeaseAcquireResult> {
  const holderId = nanoid();
  const now = new Date();
  const expiresAt = new Date(now.getTime() + LEASE_TTL_SECONDS * 1000);

  // Attempt 1: insert if no lease exists
  const insert = await db
    .prepare(
      `INSERT OR IGNORE INTO distributed_leases
         (resource_id, holder_id, acquired_at, expires_at, version)
       VALUES (?, ?, ?, ?, 1)`
    )
    .bind(resourceId, holderId, now.toISOString(), expiresAt.toISOString())
    .run();

  if (insert.meta.changes === 1) {
    return { acquired: true, holderId, expiresAt: expiresAt.toISOString() };
  }

  // Attempt 2: steal an expired lease (CAS on expiry)
  const steal = await db
    .prepare(
      `UPDATE distributed_leases
          SET holder_id   = ?,
              acquired_at = ?,
              expires_at  = ?,
              version     = version + 1
        WHERE resource_id = ?
          AND expires_at  < ?`
    )
    .bind(holderId, now.toISOString(), expiresAt.toISOString(), resourceId, now.toISOString())
    .run();

  if (steal.meta.changes === 1) {
    return { acquired: true, holderId, expiresAt: expiresAt.toISOString() };
  }

  // Contended: return current holder for observability
  const current = await db
    .prepare(
      `SELECT holder_id, expires_at
         FROM distributed_leases
        WHERE resource_id = ?`
    )
    .bind(resourceId)
    .first<{ holder_id: string; expires_at: string }>();

  return {
    acquired: false,
    holderId: current?.holder_id ?? null,
    expiresAt: current?.expires_at ?? null,
  };
}
```

---

## Renew — Heartbeat Before Expiry

```typescript
async function renewLease(
  db: D1Database,
  resourceId: string,
  holderId: string
): Promise<boolean> {
  const now = new Date();
  const newExpiry = new Date(now.getTime() + LEASE_TTL_SECONDS * 1000);

  const result = await db
    .prepare(
      `UPDATE distributed_leases
          SET expires_at = ?,
              version    = version + 1
        WHERE resource_id = ?
          AND holder_id   = ?
          AND expires_at  > ?`  // must still be valid
    )
    .bind(newExpiry.toISOString(), resourceId, holderId, now.toISOString())
    .run();

  return result.meta.changes === 1;
}
```

---

## Release — CAS Delete

```typescript
async function releaseLease(
  db: D1Database,
  resourceId: string,
  holderId: string
): Promise<boolean> {
  const result = await db
    .prepare(
      `DELETE FROM distributed_leases
        WHERE resource_id = ?
          AND holder_id   = ?`
    )
    .bind(resourceId, holderId)
    .run();

  return result.meta.changes === 1;
}
```

---

## Leader Worker — Full Lifecycle with Heartbeat

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const RESOURCE = "scheduled-job:daily-report";
    const { acquired, holderId } = await acquireLease(env.DB, RESOURCE);

    if (!acquired) {
      console.log("Lock contended, skipping run");
      return;
    }

    // Start heartbeat renewal every 10 s
    let leaseValid = true;
    const renewalInterval = setInterval(async () => {
      const renewed = await renewLease(env.DB, RESOURCE, holderId!);
      if (!renewed) {
        leaseValid = false; // lease was stolen — abort
        clearInterval(renewalInterval);
      }
    }, 10_000);

    try {
      await doWork(env, () => leaseValid); // pass liveness check
    } finally {
      clearInterval(renewalInterval);
      if (leaseValid) {
        await releaseLease(env.DB, RESOURCE, holderId!);
      }
    }
  },
};

async function doWork(
  _env: Env,
  isLeaseValid: () => boolean
): Promise<void> {
  for (let i = 0; i < 100; i++) {
    if (!isLeaseValid()) throw new Error("Lease lost during work");
    // process batch i…
    await new Promise((r) => setTimeout(r, 1000));
  }
}
```

---

## Fencing Tokens — Preventing Stale Writes

The `version` column acts as a **fencing token**. Pass it to downstream writes
so they can reject out-of-order operations from a previous lease holder:

```typescript
async function getLeaseVersion(
  db: D1Database,
  resourceId: string,
  holderId: string
): Promise<number | null> {
  const row = await db
    .prepare(
      `SELECT version FROM distributed_leases
        WHERE resource_id = ? AND holder_id = ?`
    )
    .bind(resourceId, holderId)
    .first<{ version: number }>();
  return row?.version ?? null;
}

// Include version as X-Fence-Token header on all downstream API calls
async function fencedWrite(
  url: string,
  body: unknown,
  fenceToken: number
): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Fence-Token": String(fenceToken),
    },
    body: JSON.stringify(body),
  });
}
```

---

## Anti-patterns

- **Setting TTL too short**: Causes the lock to expire mid-work under CPU
  pressure, allowing two workers to proceed simultaneously.
- **Forgetting to renew**: A single TTL with no heartbeat is fine only for
  operations guaranteed to complete before expiry.
- **Using holderId as the only guard**: Without fencing tokens, a previously
  blocked worker that resumes after lease expiry can complete stale writes.
- **Not releasing on success**: Holding the lease until expiry unnecessarily
  delays the next run; always release explicitly in the `finally` block.

---

## Gotchas

- D1 writes have ~5–20 ms latency; a 30 s TTL with 10 s heartbeat gives ample
  margin but you must not perform slow I/O between heartbeats.
- `INSERT OR IGNORE` silently succeeds with 0 changes if the row exists —
  always check `meta.changes`, not just the absence of an error.
- Workers scheduled events have a 30 s CPU time limit (50 ms on free tier);
  for long-running jobs use Durable Objects alarms instead.
- D1 is region-pinned; if you need a global lock shared across all regions,
  use a Durable Object acting as a lock coordinator.

---

## Verification

```bash
# Inspect current leases
wrangler d1 execute <DB_NAME> \
  --command "SELECT resource_id, holder_id, expires_at, version FROM distributed_leases"

# Simulate expiry by manually backdating
wrangler d1 execute <DB_NAME> \
  --command "UPDATE distributed_leases SET expires_at = '2000-01-01T00:00:00Z'"

# Confirm CAS steal succeeds after expiry
curl -X POST https://api.example.com/test/acquire-lock \
  -H "Content-Type: application/json" -d '{"resource":"test:lock"}'
```

---

## Related

- `distributed-lock-design.md`
- `fencing-tokens.md`
- `durable-object-alarm-api-scheduled-retry.md`
- `leader-election-patterns.md`
- `idempotency-design.md`

---

## Sources

- Martin Kleppmann — "How to do distributed locking" (2016)
- SQLite `INSERT OR IGNORE` and `changes()` semantics
- Cloudflare D1 documentation — Batch and transactional writes
- Leslie Lamport — Time, Clocks, and the Ordering of Events (1978)
