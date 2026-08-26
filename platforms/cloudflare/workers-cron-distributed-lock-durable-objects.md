# Distributed Lock for Cron Triggers Using Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker is triggered on a schedule (Cron Trigger), but the same cron fires concurrently on multiple Worker instances. This causes duplicate side effects: double-sends of emails, double-charges in payment flows, or double-inserts in D1. You need a distributed lock so only one instance proceeds.

## Context

Cloudflare's Cron Trigger does **not** guarantee single-instance delivery — at high frequency (e.g., `* * * * *`) or during edge-wide retries, multiple Worker instances may receive the same scheduled event simultaneously. Durable Objects provide strongly consistent, single-threaded state coordination across the edge, making them an ideal primitive for distributed locks. A `CronLock` Durable Object stores `{ owner, expiresAt }` and uses its own alarm to release the lock automatically if the holder crashes.

---

## Implementation: CronLock Durable Object + Cron Worker

```typescript
// src/cron-lock.ts  — Durable Object definition

export interface LockState {
  owner: string;
  expiresAt: number; // Unix ms
}

export class CronLock {
  private state: DurableObjectState;
  private lock: LockState | null = null;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async initialize(): Promise<void> {
    this.lock = (await this.state.storage.get<LockState>("lock")) ?? null;
  }

  async fetch(request: Request): Promise<Response> {
    await this.initialize();
    const url = new URL(request.url);

    switch (url.pathname) {
      case "/acquire": return this.handleAcquire(request);
      case "/release": return this.handleRelease(request);
      case "/status":  return this.handleStatus();
      default:        return new Response("Not Found", { status: 404 });
    }
  }

  private async handleAcquire(request: Request): Promise<Response> {
    const { owner, ttlMs = 55_000 } = await request.json<{ owner: string; ttlMs?: number }>();
    const now = Date.now();

    // If a lock exists and has not expired, reject with 409.
    if (this.lock && this.lock.expiresAt > now) {
      return Response.json(
        { locked: true, owner: this.lock.owner, expiresAt: this.lock.expiresAt },
        { status: 409 }
      );
    }

    // Acquire (or steal an expired lock).
    this.lock = { owner, expiresAt: now + ttlMs };
    await this.state.storage.put("lock", this.lock);

    // Schedule alarm to auto-release the lock at expiry.
    await this.state.storage.setAlarm(this.lock.expiresAt);

    return Response.json({ locked: false, owner, expiresAt: this.lock.expiresAt }, { status: 200 });
  }

  private async handleRelease(request: Request): Promise<Response> {
    const { owner } = await request.json<{ owner: string }>();

    if (!this.lock || this.lock.owner !== owner) {
      // Not the lock holder — ignore silently to keep operations idempotent.
      return Response.json({ released: false }, { status: 200 });
    }

    await this.state.storage.delete("lock");
    await this.state.storage.deleteAlarm();
    this.lock = null;

    return Response.json({ released: true }, { status: 200 });
  }

  private async handleStatus(): Promise<Response> {
    const now = Date.now();
    if (!this.lock || this.lock.expiresAt <= now) {
      return Response.json({ locked: false });
    }
    return Response.json({ locked: true, owner: this.lock.owner, expiresAt: this.lock.expiresAt });
  }

  // Alarm fires when the TTL expires — guaranteed release even if the holder crashes.
  async alarm(): Promise<void> {
    await this.state.storage.delete("lock");
    this.lock = null;
    console.log("CronLock: alarm fired, lock released");
  }
}
```

```typescript
// src/worker.ts  — Cron Worker that uses the lock

import { CronLock } from "./cron-lock";
export { CronLock };

export interface Env {
  CRON_LOCK: DurableObjectNamespace;
}

const LOCK_NAME = "global-cron-lock"; // single named DO instance

async function acquireLock(env: Env, owner: string, ttlMs: number): Promise<boolean> {
  const id = env.CRON_LOCK.idFromName(LOCK_NAME);
  const stub = env.CRON_LOCK.get(id);

  const res = await stub.fetch("https://do/acquire", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner, ttlMs }),
  });

  return res.status === 200; // 409 = already locked by another instance
}

async function releaseLock(env: Env, owner: string): Promise<void> {
  const id = env.CRON_LOCK.idFromName(LOCK_NAME);
  const stub = env.CRON_LOCK.get(id);

  await stub.fetch("https://do/release", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner }),
  });
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Use a unique owner per invocation so we can release exactly our lock.
    const owner = crypto.randomUUID();
    // TTL slightly shorter than cron period (55 s for a 1-minute cron).
    const acquired = await acquireLock(env, owner, 55_000);

    if (!acquired) {
      console.log("Cron: lock held by another instance, skipping.");
      return;
    }

    try {
      await doScheduledWork(env);
    } finally {
      // Always release, even on error.
      await releaseLock(env, owner);
    }
  },
};

async function doScheduledWork(_env: Env): Promise<void> {
  console.log("Cron: running scheduled work...");
  // ... your idempotent business logic here
}
```

```toml
# wrangler.toml (excerpt)
[[durable_objects.bindings]]
name = "CRON_LOCK"
class_name = "CronLock"

[triggers]
crons = ["* * * * *"]
```

---

## Lock TTL and Alarm Design

The `expiresAt` TTL serves two purposes:

1. **Crash safety** — if the holder's Worker is evicted or throws an unhandled error before calling `/release`, the DO's alarm fires at `expiresAt` and cleans up the lock automatically.
2. **Stale-lock prevention** — any subsequent cron invocation that calls `/acquire` after the TTL will steal the lock rather than waiting forever.

Set the TTL to be **slightly shorter than the cron period**. For a 1-minute cron, use 55 000 ms. For a 5-minute cron, use 280 000 ms.

---

## Anti-patterns

- **Using KV as the lock store** — KV is eventually consistent; two Workers can both read `null` and both believe the lock is free. Durable Objects are the only strongly-consistent primitive in Workers.
- **Setting TTL longer than the cron period** — if the previous job is still "locked" when the next cron fires, every invocation is skipped until manual intervention.
- **Not wrapping `doScheduledWork` in `try/finally`** — an exception before `/release` leaves the lock held until the alarm fires, wasting the rest of the period.
- **Using a random DO name per invocation** — the lock must be a single, shared DO instance (`idFromName(LOCK_NAME)`). A new DO per invocation provides no coordination.

## Gotchas

- Durable Object alarms survive DO hibernation. Even if there are no requests between cron firings, the alarm is guaranteed to fire.
- The DO's `fetch` method is invoked over the internal DO routing network, not the public internet; the URL scheme (`https://do/...`) is arbitrary — only the pathname matters.
- Cold-start latency for a DO is ~1–5 ms on the same datacenter as the cron-invoking Worker. Use `idFromName` (not `newUniqueId`) so the same DO is always reached.
- Cloudflare bills DO requests per invocation and storage per GB-month. A single named lock DO is negligible cost.

## Verification

```bash
# Tail live logs to confirm only one instance proceeds
wrangler tail --format pretty

# On a 1-minute cron you should see exactly one of:
# "Cron: running scheduled work..."
# and zero or more:
# "Cron: lock held by another instance, skipping."

# Check lock status manually via the DO HTTP endpoint (requires a test route)
curl https://your-worker.example.com/lock-status
# {"locked":false}  — between cron runs
```

## Related

- `workers-analytics-engine-custom-dashboard.md`
- `workers-durable-objects-basics.md`
- `r2-presigned-url-upload-workers.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
