# Distributed Lock Pattern with Durable Objects

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Multiple Workers instances race to perform a non-idempotent mutation — provisioning a
tenant's first database row, sending a one-time welcome email, or processing a billing
event exactly once. Without coordination, concurrent requests all win the race and the
operation is duplicated. A traditional mutex is unavailable because Workers are
stateless and share no in-process memory.

## Context

Cloudflare Durable Objects (DOs) have two properties that make them a natural
distributed lock primitive:

1. **Single-threaded execution**: a DO processes one request at a time; the runtime
   serialises concurrent `fetch()` calls to the same object.
2. **Global uniqueness**: a DO with a given ID/name runs in exactly one location
   world-wide at any instant.

These properties let you build a lock without external coordination — the DO _is_ the
critical section.

The pattern has three phases: **acquire**, **execute critical section**, **release**.
A TTL on every lock prevents deadlocks when the holder crashes mid-operation.

## Acquiring and Releasing the Lock

```typescript
// lock-object.ts  — the Durable Object
export class DistributedLock implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const action = url.pathname.slice(1); // "acquire" | "release" | "status"

    if (action === "acquire") {
      return this.state.blockConcurrencyWhile(() => this.handleAcquire(request));
    }
    if (action === "release") {
      return this.state.blockConcurrencyWhile(() => this.handleRelease(request));
    }
    if (action === "status") {
      const held = await this.state.storage.get<boolean>("held");
      const ttl  = await this.state.storage.get<number>("expiresAt");
      return Response.json({ held: !!held, expiresAt: ttl ?? null });
    }
    return new Response("Not found", { status: 404 });
  }

  private async handleAcquire(request: Request): Promise<Response> {
    const { owner, ttlMs = 30_000 } = await request.json<{
      owner: string;
      ttlMs?: number;
    }>();

    const held      = await this.state.storage.get<boolean>("held");
    const expiresAt = await this.state.storage.get<number>("expiresAt");
    const now       = Date.now();

    // Expired locks are auto-released
    if (held && expiresAt && now > expiresAt) {
      await this.state.storage.delete("held");
      await this.state.storage.delete("owner");
      await this.state.storage.delete("expiresAt");
    }

    const stillHeld = await this.state.storage.get<boolean>("held");
    if (stillHeld) {
      return Response.json({ acquired: false }, { status: 409 });
    }

    await this.state.storage.put("held",      true);
    await this.state.storage.put("owner",     owner);
    await this.state.storage.put("expiresAt", now + ttlMs);

    // Schedule auto-release via alarm
    await this.state.storage.setAlarm(now + ttlMs);

    return Response.json({ acquired: true, expiresAt: now + ttlMs });
  }

  private async handleRelease(request: Request): Promise<Response> {
    const { owner } = await request.json<{ owner: string }>();
    const storedOwner = await this.state.storage.get<string>("owner");

    if (storedOwner !== owner) {
      return Response.json({ released: false, reason: "not-owner" }, { status: 403 });
    }

    await this.state.storage.delete("held");
    await this.state.storage.delete("owner");
    await this.state.storage.delete("expiresAt");
    await this.state.storage.deleteAlarm();

    return Response.json({ released: true });
  }

  async alarm(): Promise<void> {
    // TTL expired — forcibly release
    await this.state.storage.delete("held");
    await this.state.storage.delete("owner");
    await this.state.storage.delete("expiresAt");
  }
}
```

## Using the Lock from a Worker

```typescript
// worker.ts
import { Env } from "./types";

const LOCK_TTL_MS  = 30_000;
const ACQUIRE_POLL = 200;   // ms between retry attempts
const MAX_WAIT_MS  = 5_000; // give up after 5 s

async function withLock<T>(
  env: Env,
  lockName: string,
  fn: () => Promise<T>
): Promise<T> {
  const id     = env.DISTRIBUTED_LOCK.idFromName(lockName);
  const stub   = env.DISTRIBUTED_LOCK.get(id);
  const owner  = crypto.randomUUID();
  const start  = Date.now();

  // Acquire with spin-wait
  while (true) {
    const res = await stub.fetch("https://lock/acquire", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner, ttlMs: LOCK_TTL_MS }),
    });

    if (res.ok) break; // acquired

    if (Date.now() - start > MAX_WAIT_MS) {
      throw new Error(`Lock "${lockName}" not acquired within ${MAX_WAIT_MS}ms`);
    }

    // Back off before retrying — avoid thundering-herd on contended locks
    await new Promise(r => setTimeout(r, ACQUIRE_POLL + Math.random() * 100));
  }

  try {
    return await fn();
  } finally {
    // Best-effort release; alarm is the safety net if this fails
    await stub.fetch("https://lock/release", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner }),
    });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenantId = new URL(request.url).searchParams.get("tenant") ?? "default";

    const result = await withLock(env, `provision:${tenantId}`, async () => {
      // This block runs at most once concurrently per tenantId
      return await provisionTenant(env, tenantId);
    });

    return Response.json(result);
  },
};
```

## Lock Observability and Health Check

```typescript
// health-check route embedded in the main Worker
async function lockStatus(env: Env, lockName: string): Promise<Response> {
  const id   = env.DISTRIBUTED_LOCK.idFromName(lockName);
  const stub = env.DISTRIBUTED_LOCK.get(id);
  const res  = await stub.fetch("https://lock/status");
  const data = await res.json<{ held: boolean; expiresAt: number | null }>();

  return Response.json({
    lock:      lockName,
    held:      data.held,
    expiresAt: data.expiresAt ? new Date(data.expiresAt).toISOString() : null,
    ttlRemaining: data.expiresAt
      ? Math.max(0, data.expiresAt - Date.now())
      : null,
  });
}
```

```toml
# wrangler.toml
[[durable_objects.bindings]]
name       = "DISTRIBUTED_LOCK"
class_name = "DistributedLock"

[[migrations]]
tag           = "v1"
new_classes   = ["DistributedLock"]
```

## Anti-patterns

- **Lock without TTL / alarm**: a Worker that crashes after acquiring and before
  releasing leaves the lock held forever. Always set a TTL and back it with a DO alarm.
- **Using KV as the lock store**: KV has eventual consistency; two Workers can both
  read "not held" before either write propagates, defeating mutual exclusion entirely.
- **Lock scope too broad**: locking on `"global"` instead of a per-resource key
  serialises all traffic. Scope locks to the narrowest necessary resource ID.
- **Holding the lock across external calls**: if the critical section awaits an
  external HTTP call that may hang, you inflate lock hold time and increase contention.
  Fetch external data _before_ acquiring the lock; only write state inside it.
- **Ignoring the `not-owner` error on release**: always verify the release succeeded.
  If another process acquired the lock mid-flight (TTL expired), releasing a lock you
  no longer own is silently skipped — that is correct behavior, not a bug.

## Gotchas

- **DO cold start latency**: the first request to a DO after it has hibernated incurs
  a cold-start penalty (~10–50 ms extra). Budget for this in timeout calculations.
- **`blockConcurrencyWhile` is required**: without it, concurrent acquire requests to
  the same DO can interleave between the read-then-write steps, causing a race inside
  the DO itself. Wrap any multi-step storage operation in `blockConcurrencyWhile`.
- **Alarm delivery is at-least-once**: alarms may fire more than once. Make the
  alarm handler idempotent (deleting already-absent keys is harmless).
- **DO ID vs name**: use `idFromName(lockName)` rather than a random ID so the same
  lock name always resolves to the same DO instance across Workers.
- **Free tier DO limits**: the Workers Free plan has no Durable Objects; this pattern
  requires Workers Paid.

## Verification

```bash
# 1. Fire 10 concurrent requests targeting the same lock
for i in $(seq 1 10); do
  curl -s "https://your-worker.dev/provision?tenant=acme" &
done
wait

# 2. Only one request should return { "created": true }; others { "alreadyExists": true }
# Inspect lock status directly
curl "https://your-worker.dev/lock-status?lock=provision:acme"

# 3. Simulate crash: acquire lock, kill Worker, wait > TTL, verify lock auto-released
curl -s "https://your-worker.dev/provision?tenant=crash-test"
sleep 35
curl "https://your-worker.dev/lock-status?lock=provision:crash-test"
# expected: { "held": false }
```

## Related

- `token-bucket-durable-objects.md` — per-key rate limiting with DO
- `per-tenant-durable-object.md` — tenancy isolation with DO
- `idempotency-key-pattern-workers-d1.md` — idempotency at the DB layer
- `leader-election.md` — electing a single coordinator (related but broader)
- `lease-based-concurrency-d1.md` — SQL-level lease alternative when DO is unavailable

## Sources

- Cloudflare Durable Objects documentation — blockConcurrencyWhile
  https://developers.cloudflare.com/durable-objects/api/state/#blockconcurrencywhile
- Cloudflare DO Alarms API
  https://developers.cloudflare.com/durable-objects/api/alarms/
- Martin Kleppmann, "Designing Data-Intensive Applications", Chapter 8 — Distributed Locks
- Redlock algorithm (for comparison with single-node DO approach)
  https://redis.io/docs/latest/develop/use/patterns/distributed-locks/
