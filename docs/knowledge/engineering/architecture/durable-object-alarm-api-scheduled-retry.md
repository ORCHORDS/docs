# Durable Object Alarm API for Reliable Scheduled Work and Retry Orchestration

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Cloudflare Workers application needs to schedule future work that must fire reliably
even when no external traffic is arriving — periodic cleanups, delayed push notifications,
subscription billing checks, retry back-offs, or session expiry. Cloudflare Cron Triggers
fire Workers on a cron schedule, but they offer no per-entity granularity and share a
single invocation budget. The Durable Object Alarm API gives each DO instance its own
persistent timer that fires a dedicated `alarm()` handler — enabling per-entity, per-job
scheduling with millisecond precision from within the same stateful object that owns the
data being processed.

Concrete triggers for the example project / example.com stack:
- Send a push notification exactly 24 h after a user saves a chord progression
- Retry a failed third-party webhook delivery with exponential back-off
- Expire a temporary share-link token at a precise future timestamp
- Run a daily subscription-status sync per tenant without a monolithic cron Worker

---

## Context

The Alarm API is part of the Durable Objects runtime (not Workers in general). An alarm
is a single future timestamp stored durably alongside the DO's storage. When the clock
reaches that timestamp, Cloudflare wakes the DO and calls `alarm()` on the class instance,
even if the DO was evicted between when it was set and when it fires. Only one alarm can
be active at a time per DO instance, but a DO can re-arm itself inside `alarm()` to
create recurring or chained schedules.

Key properties:
- **Durability**: alarm timestamp survives evictions and container restarts
- **Exactly-once delivery**: Cloudflare guarantees the alarm fires at least once; the DO
  runtime suppresses duplicate deliveries
- **No external scheduler**: fully managed, zero infrastructure overhead
- **Per-instance granularity**: a DO per user / per job / per tenant gets its own timer

---

## Architecture Patterns

### Pattern A — Per-entity alarm (delayed notification)

```
Client Request
    │  PUT /path/to/reminder { delayMs: 86400000 }
    ▼
Edge Worker
    │  get DO stub for user-{id}
    │  POST https://do/set-alarm { fireAt: now + delayMs }
    ▼
UserAlarmDO
    │  ctx.storage.setAlarm(fireAt)
    │  ...time passes...
    ▼ alarm() fires
    │  fetch payload from storage
    │  POST https://push-worker/send { userId, message }
    ▼
Push Worker ──▶ FCM/APNs ──▶ React Native device
```

### Pattern B — Exponential back-off retry chain

```
DO.fetch("/execute")
    │  attempt task
    │  on failure: set alarm for now + backoff(attempts)
    ▼  ...alarm fires...
DO.alarm()
    │  retry task
    │  if success: done
    │  if attempts < max: set alarm for next back-off
    │  if exhausted: write to D1 dead-letter table
```

### Pattern C — Recurring per-tenant schedule (no cron trigger)

```
TenantSchedulerDO.alarm()
    │  do work (sync subscription status)
    │  ctx.storage.setAlarm(Date.now() + INTERVAL_MS)  // re-arm
```

---

## Implementation

### Generic Alarm DO Base

```typescript
// src/do/alarm-base.ts
import { DurableObject } from 'cloudflare:workers';

export abstract class AlarmBaseDO extends DurableObject {
  /**
   * Subclasses implement this with the work to do on each alarm.
   * Return true to re-arm with the same interval, or return a new Date to
   * schedule the next alarm, or return null to stop.
   */
  protected abstract onAlarm(): Promise<Date | boolean | null>;

  async alarm(): Promise<void> {
    const next = await this.onAlarm();
    if (next === true) {
      // Caller wants to re-arm; interval must be stored by the subclass
      const interval = await this.ctx.storage.get<number>('interval');
      if (interval) await this.ctx.storage.setAlarm(Date.now() + interval);
    } else if (next instanceof Date) {
      await this.ctx.storage.setAlarm(next);
    }
    // null or false → alarm stops
  }
}
```

### Delayed Push Notification DO

```typescript
// src/do/notification-alarm.ts
import { AlarmBaseDO } from './alarm-base';

interface NotificationPayload {
  userId: string;
  deviceToken: string;
  title: string;
  body: string;
}

interface Env {
  NOTIFICATION_ALARM: DurableObjectNamespace;
  PUSH_WORKER: Fetcher; // Service binding to push Worker
}

export class NotificationAlarmDO extends AlarmBaseDO {
  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/schedule' && request.method === 'POST') {
      const { fireAt, payload } = await request.json<{
        fireAt: number; // Unix ms
        payload: NotificationPayload;
      }>();

      await this.ctx.storage.put('payload', payload);
      await this.ctx.storage.setAlarm(fireAt);

      return Response.json({ ok: true, fireAt });
    }

    if (url.pathname === '/cancel' && request.method === 'DELETE') {
      await this.ctx.storage.deleteAlarm();
      await this.ctx.storage.delete('payload');
      return Response.json({ ok: true });
    }

    if (url.pathname === '/status') {
      const alarm = await this.ctx.storage.getAlarm();
      const payload = await this.ctx.storage.get<NotificationPayload>('payload');
      return Response.json({ alarm, hasPayload: !!payload });
    }

    return new Response('Not found', { status: 404 });
  }

  protected async onAlarm(): Promise<null> {
    const payload = await this.ctx.storage.get<NotificationPayload>('payload');
    if (!payload) return null;

    const env = this.env as Env;
    try {
      const res = await env.PUSH_WORKER.fetch('https://push/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Push failed: ${res.status}`);
      await this.ctx.storage.delete('payload'); // Clean up after success
    } catch (err) {
      // Re-arm with a 5-minute retry — simple fixed delay
      await this.ctx.storage.setAlarm(Date.now() + 5 * 60 * 1000);
      console.error('Notification alarm failed, will retry in 5 min:', err);
    }
    return null; // Base class will not re-arm; we manage it manually above
  }
}
```

### Exponential Back-off Retry DO

```typescript
// src/do/retry-alarm.ts
import { DurableObject } from 'cloudflare:workers';

interface RetryState {
  attempts: number;
  maxAttempts: number;
  jobType: string;
  payload: unknown;
  lastError?: string;
}

export class RetryAlarmDO extends DurableObject {
  async fetch(request: Request): Promise<Response> {
    if (request.method === 'POST') {
      const { jobType, payload, maxAttempts = 5 } = await request.json<{
        jobType: string;
        payload: unknown;
        maxAttempts?: number;
      }>();

      const state: RetryState = { attempts: 0, maxAttempts, jobType, payload };
      await this.ctx.storage.put('state', state);
      // Fire immediately (1 ms in the future)
      await this.ctx.storage.setAlarm(Date.now() + 1);
      return Response.json({ ok: true });
    }
    return new Response('Method not allowed', { status: 405 });
  }

  async alarm(): Promise<void> {
    const state = await this.ctx.storage.get<RetryState>('state');
    if (!state) return;

    state.attempts += 1;

    try {
      await this.dispatch(state.jobType, state.payload);
      // Success — delete state, do not re-arm
      await this.ctx.storage.delete('state');
    } catch (err: unknown) {
      state.lastError = String(err);
      if (state.attempts < state.maxAttempts) {
        const backoffMs = this.calcBackoff(state.attempts);
        await this.ctx.storage.put('state', state);
        await this.ctx.storage.setAlarm(Date.now() + backoffMs);
      } else {
        // Write to dead-letter — implementation calls out to a Worker binding
        await this.writeDead(state);
        await this.ctx.storage.delete('state');
      }
    }
  }

  private calcBackoff(attempt: number): number {
    // 2^attempt seconds with ±10% jitter, max 5 min
    const base = Math.pow(2, attempt) * 1000;
    const jitter = base * 0.1 * (Math.random() * 2 - 1);
    return Math.min(base + jitter, 5 * 60 * 1000);
  }

  private async dispatch(jobType: string, payload: unknown): Promise<void> {
    // Route to job-type-specific logic or a service binding
    throw new Error('dispatch must be implemented by subclass or composition');
  }

  private async writeDead(state: RetryState): Promise<void> {
    // Write exhausted jobs to D1 dead-letter table
    console.error('Job exhausted retries', JSON.stringify(state));
  }
}
```

### Recurring Per-tenant Scheduler DO

```typescript
// src/do/tenant-scheduler.ts
import { DurableObject } from 'cloudflare:workers';

const SYNC_INTERVAL_MS = 24 * 60 * 60 * 1000; // 24 h

interface Env {
  DB: D1Database;
  TENANT_SCHEDULER: DurableObjectNamespace;
}

export class TenantSchedulerDO extends DurableObject {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const tenantId = url.searchParams.get('tenantId');
    if (!tenantId) return new Response('tenantId required', { status: 400 });

    if (url.pathname === '/start') {
      await this.ctx.storage.put('tenantId', tenantId);
      // First run: fire in 1 minute, then daily
      await this.ctx.storage.setAlarm(Date.now() + 60_000);
      return Response.json({ ok: true, firstRun: new Date(Date.now() + 60_000).toISOString() });
    }

    if (url.pathname === '/stop') {
      await this.ctx.storage.deleteAlarm();
      return Response.json({ ok: true });
    }

    return new Response('Not found', { status: 404 });
  }

  async alarm(): Promise<void> {
    const tenantId = await this.ctx.storage.get<string>('tenantId');
    if (!tenantId) return;

    const env = this.env as Env;
    await syncSubscriptionStatus(tenantId, env.DB);

    // Re-arm for the next day
    await this.ctx.storage.setAlarm(Date.now() + SYNC_INTERVAL_MS);
  }
}

async function syncSubscriptionStatus(tenantId: string, db: D1Database): Promise<void> {
  await db
    .prepare('UPDATE tenants SET last_synced = ? WHERE id = ?')
    .bind(new Date().toISOString(), tenantId)
    .run();
}
```

---

## D1 Dead-Letter Schema

```sql
CREATE TABLE alarm_dead_letters (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  do_name     TEXT NOT NULL,
  job_type    TEXT NOT NULL,
  payload     TEXT NOT NULL,  -- JSON
  attempts    INTEGER NOT NULL,
  last_error  TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  INDEX idx_adl_job_type (job_type),
  INDEX idx_adl_created  (created_at)
);
```

---

## wrangler.toml Configuration

```toml
[[durable_objects.bindings]]
name = "NOTIFICATION_ALARM"
class_name = "NotificationAlarmDO"

[[durable_objects.bindings]]
name = "TENANT_SCHEDULER"
class_name = "TenantSchedulerDO"

[[migrations]]
tag = "v1"
new_classes = ["NotificationAlarmDO", "TenantSchedulerDO", "RetryAlarmDO"]

# Service binding for push notifications
[[services]]
binding = "PUSH_WORKER"
service = "push-gateway"
```

---

## Mobile API Consumer Considerations (example project React Native)

React Native clients should interact with alarm-backed DOs only through typed REST
endpoints on an edge Worker — never directly via DO URLs.

```typescript
// Ingress Worker — schedule a reminder
router.put('/v1/path/to/reminders', async (req, env) => {
  const { userId } = req.params;
  const { message, delayMs } = await req.json();

  // Use userId as the DO name for deterministic routing
  const doId = env.NOTIFICATION_ALARM.idFromName(`user-${userId}`);
  const stub = env.NOTIFICATION_ALARM.get(doId);

  const res = await stub.fetch('https://do/schedule', {
    method: 'POST',
    body: JSON.stringify({
      fireAt: Date.now() + delayMs,
      payload: { userId, ...message },
    }),
  });

  return new Response(await res.text(), { status: res.status });
});
```

The app cancels a reminder via `DELETE /v1/path/to/reminders`, which calls the
DO's `/cancel` endpoint. This pattern keeps the alarm lifecycle fully server-side —
the app does not need to track alarm IDs or manage retries.

---

## Anti-patterns

- **Using Cron Triggers for per-entity schedules**: A single cron fires one Worker that
  must iterate all users. This creates a hot Worker for large user bases and couples all
  entities to the same timer resolution.
- **Calling `setAlarm` inside `blockConcurrencyWhile`**: Alarm mutations happen
  outside storage transactions. Set alarms after `blockConcurrencyWhile` resolves.
- **Relying on sub-second precision**: Alarms have ~1 second delivery precision. Do
  not use them for sub-second timing (use `setTimeout` within an active request instead).
- **Not re-arming inside `alarm()` after a failure**: If `alarm()` throws, the DO
  runtime does NOT automatically reschedule. Wrap the entire body in try/catch and
  set the next alarm before throwing.
- **Long-running `alarm()` handlers**: The alarm handler is subject to the same 30-second
  CPU time limit as regular fetch handlers. Offload heavy work to a queue.
- **Multiple alarms per DO**: Each DO has one alarm slot. Use a priority queue in
  storage if you need to schedule multiple future events from the same DO instance.

---

## Gotchas

- `ctx.storage.getAlarm()` returns `null` if no alarm is set, not `undefined`.
- Deleting a DO's alarm with `deleteAlarm()` is idempotent; calling it when no alarm is
  set is a no-op.
- Alarm timestamps are in Unix milliseconds (same as `Date.now()`), not seconds.
- During a Cloudflare outage, alarm delivery may be delayed but not permanently lost.
- If you rename a DO class and migrate, existing alarms on old instances are abandoned.
- The alarm fires the DO into a fresh execution context — any in-memory state is gone.
  Read all state from `ctx.storage` at the start of `alarm()`.

---

## Verification

```bash
# Schedule a test notification 10 seconds in the future
curl -X PUT https://api.example.com/v1/path/to/reminders \
  -H "Content-Type: application/json" \
  -d '{"delayMs": 10000, "message": {"title": "Test", "body": "Alarm fired!"}}'

# Check alarm status
curl https://do-dev.internal/status
# Expected: { "alarm": <epoch_ms>, "hasPayload": true }

# Wait 15 seconds, then verify push log in D1
wrangler d1 execute DB --command \
  "SELECT * FROM push_log WHERE user_id = 'test-user' ORDER BY sent_at DESC LIMIT 1;"

# Verify dead-letter is empty for this user
wrangler d1 execute DB --command \
  "SELECT * FROM alarm_dead_letters WHERE do_name LIKE '%test-user%';"
```

---

## Related

- `competing-consumers-durable-objects.md` — Durable Objects for distributed task claiming
- `retry-pattern.md` — generic retry strategies
- `dead-letter-queue-architecture.md` — exhausted job handling
- `workers-do-websocket-architecture.md` — other DO runtime capabilities
- `notification-system-design.md` — push notification architecture
- `at-least-once-delivery.md` — delivery guarantees

---

## Sources

- Cloudflare Durable Objects Alarm API (developers.cloudflare.com/durable-objects/api/alarms)
- Cloudflare Workers runtime limits
- Enterprise Integration Patterns — Hohpe & Woolf (2003), "Scheduler" pattern
- AWS re:Invent 2022 — Serverless retry strategies (analogous patterns)
