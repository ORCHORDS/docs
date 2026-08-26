# Durable Objects: Distributed Lock and Leader Election

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Multiple Worker instances need to coordinate access to a shared resource — a third-party
API with strict rate limits, a singleton background task, or a critical section of a
database write sequence. Without coordination, concurrent Workers race, duplicate work, or
exceed API quotas. You need a distributed lock and/or a deterministic leader that all Workers
can agree on without an external coordination service.

## Context

Durable Objects are the natural coordination primitive on Cloudflare: each named instance
runs in exactly one location at a time and processes requests sequentially. This property
makes them an ideal lock server: the DO is the lock, and holding a request open is holding
the lock.

Two patterns build on this:

- **Mutex / Distributed lock** — a Worker acquires the lock, does critical work, then
  releases it. Other Workers queue behind an in-progress RPC call and are unblocked in order.
- **Leader election** — one Worker at a time is designated leader and performs a recurring
  task (e.g. polling an external API, ticking a game loop). The others detect the leader's
  heartbeat and stand by; they campaign only when the heartbeat lapses.

Both patterns use Durable Object SQLite storage (available after the `2024-04-03` compatibility
date) for persistence across evictions and Alarms for TTL-based expiry.

## Mutex / Distributed Lock DO

```typescript
// src/lock.ts
import { DurableObject } from "cloudflare:workers";

interface LockState {
  holder: string | null;
  acquiredAt: number | null;
  ttlMs: number;
}

export class DistributedLock extends DurableObject {
  private sql: SqlStorage;

  constructor(ctx: DurableObjectState, env: unknown) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS lock (
        id      INTEGER PRIMARY KEY CHECK (id = 1),
        holder  TEXT,
        acquired_at INTEGER,
        ttl_ms  INTEGER NOT NULL DEFAULT 10000
      );
      INSERT OR IGNORE INTO lock (id, holder, acquired_at) VALUES (1, NULL, NULL);
    `);
  }

  /** Returns true if acquired, false if already held by another caller. */
  async acquire(callerId: string, ttlMs = 10_000): Promise<boolean> {
    const now = Date.now();
    const rows = this.sql.exec<LockRow>("SELECT holder, acquired_at, ttl_ms FROM lock WHERE id = 1").toArray();
    const row = rows[0];

    const isExpired = row.holder !== null &&
      row.acquired_at !== null &&
      now - row.acquired_at > row.ttl_ms;

    if (row.holder !== null && !isExpired && row.holder !== callerId) {
      return false; // lock held by someone else
    }

    this.sql.exec(
      "UPDATE lock SET holder = ?, acquired_at = ?, ttl_ms = ? WHERE id = 1",
      callerId, now, ttlMs,
    );

    // Set an alarm to auto-release if the holder crashes
    await this.ctx.storage.setAlarm(now + ttlMs);
    return true;
  }

  async release(callerId: string): Promise<boolean> {
    const rows = this.sql.exec<LockRow>("SELECT holder FROM lock WHERE id = 1").toArray();
    if (rows[0]?.holder !== callerId) return false; // not the holder

    this.sql.exec("UPDATE lock SET holder = NULL, acquired_at = NULL WHERE id = 1");
    await this.ctx.storage.deleteAlarm();
    return true;
  }

  async alarm(): Promise<void> {
    // TTL expired — force-release the lock
    this.sql.exec("UPDATE lock SET holder = NULL, acquired_at = NULL WHERE id = 1");
  }
}

interface LockRow { holder: string | null; acquired_at: number | null; ttl_ms: number; }
```

## Lock Client in a Worker

```typescript
// src/index.ts
interface Env {
  LOCK: DurableObjectNamespace;
}

const LOCK_ID = "global-api-lock"; // all Workers use the same name

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const lock = env.LOCK.get(env.LOCK.idFromName(LOCK_ID));
    const callerId = crypto.randomUUID();

    // Retry up to 5 times with 200 ms backoff
    let acquired = false;
    for (let attempt = 0; attempt < 5; attempt++) {
      acquired = await lock.acquire(callerId, 10_000) as boolean;
      if (acquired) break;
      await scheduler.wait(200 * (attempt + 1));
    }

    if (!acquired) {
      return new Response("Lock unavailable — try again", { status: 503 });
    }

    try {
      const result = await doProtectedWork();
      return Response.json({ result });
    } finally {
      await lock.release(callerId);
    }
  },
};

async function doProtectedWork(): Promise<string> {
  // Replace with your rate-limited API call or critical section
  return "done";
}
```

## Leader Election DO

```typescript
// src/leader.ts
import { DurableObject } from "cloudflare:workers";

const LEASE_MS = 30_000;   // leader holds for 30 s
const HEARTBEAT_MS = 10_000; // leader must heartbeat every 10 s

export class LeaderElection extends DurableObject {
  private sql: SqlStorage;

  constructor(ctx: DurableObjectState, env: unknown) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS leader (
        id          INTEGER PRIMARY KEY CHECK (id = 1),
        candidate   TEXT,
        last_beat   INTEGER
      );
      INSERT OR IGNORE INTO leader (id, candidate, last_beat) VALUES (1, NULL, NULL);
    `);
  }

  /** Returns { leader, isMe } — candidates campaign by calling this repeatedly. */
  async campaign(candidateId: string): Promise<{ leader: string | null; isMe: boolean }> {
    const now = Date.now();
    const [row] = this.sql.exec<LeaderRow>(
      "SELECT candidate, last_beat FROM leader WHERE id = 1"
    ).toArray();

    const leaderAlive = row.candidate !== null &&
      row.last_beat !== null &&
      now - row.last_beat < LEASE_MS;

    if (leaderAlive && row.candidate !== candidateId) {
      return { leader: row.candidate, isMe: false };
    }

    // Either no leader, lease expired, or re-electing self
    this.sql.exec(
      "UPDATE leader SET candidate = ?, last_beat = ? WHERE id = 1",
      candidateId, now,
    );
    await this.ctx.storage.setAlarm(now + LEASE_MS);
    return { leader: candidateId, isMe: true };
  }

  /** Current leader must heartbeat to maintain the lease. */
  async heartbeat(candidateId: string): Promise<boolean> {
    const [row] = this.sql.exec<LeaderRow>(
      "SELECT candidate FROM leader WHERE id = 1"
    ).toArray();

    if (row.candidate !== candidateId) return false;

    const now = Date.now();
    this.sql.exec("UPDATE leader SET last_beat = ? WHERE id = 1", now);
    await this.ctx.storage.setAlarm(now + LEASE_MS);
    return true;
  }

  async alarm(): Promise<void> {
    // Lease expired — clear the leader
    this.sql.exec("UPDATE leader SET candidate = NULL, last_beat = NULL WHERE id = 1");
  }
}

interface LeaderRow { candidate: string | null; last_beat: number | null; }
```

## Leader Worker — Campaign and Run Task

```typescript
// src/leader-worker.ts
interface Env {
  ELECTION: DurableObjectNamespace;
}

const ELECTION_ID = "cron-leader";

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const el = env.ELECTION.get(env.ELECTION.idFromName(ELECTION_ID));
    const id = "worker-" + crypto.randomUUID();

    const { isMe } = await el.campaign(id) as { leader: string; isMe: boolean };
    if (!isMe) return; // another Worker won — do nothing

    try {
      await runLeaderTask();

      // Heartbeat loop — keep the lease alive while work is in progress
      const hbInterval = setInterval(async () => {
        const ok = await el.heartbeat(id) as boolean;
        if (!ok) clearInterval(hbInterval); // lost leadership — stop
      }, HEARTBEAT_MS);

      await runLeaderTask();
      clearInterval(hbInterval);
    } finally {
      // Graceful abdication — release the lease so successors campaign immediately
      await el.campaign(""); // empty string never matches, causes expiry on next alarm
    }
  },
};

async function runLeaderTask() {
  // Replace with your singleton task: API poll, queue drain, cache warm, etc.
}
```

## Anti-patterns

- Using KV for locking — KV is eventually consistent and has no compare-and-swap; two Writers
  can both read "no lock" simultaneously and both proceed.
- Using the DO alarm as the sole lock mechanism without persisting the holder — if the DO is
  evicted before the alarm fires, state is lost and the lock is silently orphaned.
- Long critical sections without a TTL — if the holder crashes before releasing, the lock
  hangs forever; always set a TTL and back it with an alarm.
- Creating one DO per lock acquisition — use a fixed name (`idFromName`) so all Workers share
  the same instance; unique IDs create unrelated instances that do not coordinate.

## Gotchas

- DO RPC calls are serialised within the instance, but the `acquire` → `doWork` → `release`
  sequence is not atomic across RPC boundaries; design for the case where the Worker crashes
  between acquire and release.
- `setAlarm` is a persistent side effect — if a Worker calls `acquire` but the DO is evicted
  mid-call, the alarm may fire before the holder releases, causing a spurious force-release.
  Idempotent critical sections are safer than assuming at-most-once execution.
- The Durable Object SQLite `2024-04-03` compatibility date must be set in `wrangler.toml`;
  older namespaces use the legacy key-value store and the SQL API is unavailable.

## Verification

```bash
# Confirm two concurrent lock acquires return exactly one success
for i in 1 2; do
  curl -s -X POST https://your-worker.example.com/work &
done
wait
# One response should be 200 {"result":"done"}, the other 503

# Confirm the lock auto-releases after TTL (set a short TTL in dev, e.g. 2 s)
curl -X POST https://your-worker.example.com/work?ttl=2000
sleep 3
curl -X POST https://your-worker.example.com/work
# Second request should succeed without waiting
```

## Related

- `durable-objects-best-practices.md`
- `durable-objects-sqlite-storage.md`
- `durable-objects-alarms.md`
- `durable-objects-rate-limiter-pattern.md`
- `workers-rpc-service-binding-patterns.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/sql-storage/
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/durable-objects/best-practices/create-durable-object-stubs-and-send-requests/
